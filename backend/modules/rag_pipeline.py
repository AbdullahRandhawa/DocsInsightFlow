import httpx
import json
import logging
from core.config import settings
from modules.retriever import retrieve_relevant_chunks, build_context_string

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# ROUTER PROMPT
# ──────────────────────────────────────────────────────────────────────────────
ROUTER_PROMPT = """SYSTEM: You are the core traffic controller for DocsInsightFlow, a high-performance document intelligence SaaS. Your job is to determine if the user's latest message requires a vector database retrieval (Pinecone) to get specific facts, or if it can be answered immediately using the existing context.

You are provided with:
1. The Global Document Summary (high-level overview of the entire file).
2. The Live Chat History (the context of what has already been said).
3. The New User Message.

CRITICAL EVALUATION LOGIC:
- SET "needs_vector_search" TO false ONLY IF:
  * The user is making small talk, greeting you, saying thanks, or asking meta-questions about the app itself.
  * The user is asking a high-level macro question perfectly covered by the Global Document Summary.
  * The user is asking a direct follow-up to information that is completely visible within the recent Chat History. If the text in the history already contains 100% of the answer, do not search.
  **IF FALSE: You MUST generate the final answer yourself in the "response" field based on the Summary and History.**

- SET "needs_vector_search" TO true IF:
  * The user is asking for specific facts, metrics, tools, names, technical architecture, rules, or data points that require diving deep into the document's chunks.
  * AMBIGUITY RULE: If you are at all uncertain whether the history/summary contains the full answer, ALWAYS default to true.

QUERY REWRITING RULES (Only execute if "needs_vector_search" is true):
- Strip out conversational fluff.
- Resolve all pronouns (it, this, that, they) using the Chat History.
- MANDATORY: Preserve all technical proper nouns exactly as written.
- Expand vague terminology into domain-specific keywords.

OUTPUT FORMAT:
Return raw JSON only. No markdown formatting blocks, no backticks, no explanations. 

Expected JSON Structure:
{
  "needs_vector_search": true,
  "optimized_query": "Standalone query string with resolved pronouns and preserved entities"
}
OR
{
  "needs_vector_search": false,
  "response": "Your full, complete, generated answer to the user's message, drawn from the Global Summary and Chat History."
}
"""

# ──────────────────────────────────────────────────────────────────────────────
# GENERATOR PROMPT
# ──────────────────────────────────────────────────────────────────────────────
GENERATOR_PROMPT = """You are DocsInsightFlow, an expert document analysis assistant. Your primary goal is to find answers within the provided context, even if they are buried or phrased differently than the user's question.

You will receive:
1. <GLOBAL_SUMMARY>: A structured overview of the document(s).
2. <CONTEXT_BLOCKS>: Specific excerpts retrieved via vector search.
3. Chat History: Recent conversational context.


GENERAL KNOWLEDGE CLAUSE:
- If the user's message is a general question (a greeting, a request for coding help, a conceptual question, etc.) that has absolutely no connection to the uploaded documents, you are permitted to answer it helpfully using your general knowledge.
- HOWEVER, after giving the answer, you MUST add a short, friendly reminder at the end. For example: "By the way, my core purpose is to help you analyze and extract insights from your uploaded documents. Feel free to ask me anything about them!"
- Never refuse to answer a general question outright. Always be helpful first, then redirect.

YOUR ANALYSIS PROCESS:
1. DEEP SEARCH: Read every single word of the <CONTEXT_BLOCKS> and <GLOBAL_SUMMARY>. Look for synonyms, related concepts, or partial matches to the user's query. You must try hard to find the answer.
2. SYNTHESIZE: Combine information from multiple blocks or the summary to form a complete answer. If the user asks for a list (like tools or requirements), extract every single item you can find.
3. FALLBACK: ONLY if you have exhaustively searched the context and the answer is truly, 100% missing, politely inform the user that the specific information wasn't found in the retrieved sections of the document. Then, act as a helpful guide: suggest they try rephrasing the question with different keywords, or mention they can adjust the search settings (like lowering the threshold or increasing top_k) to cast a wider net. Do NOT use a robotic, hardcoded response.

STRICT RULES:
- Rely strictly on the provided context. Do NOT invent facts.
- Answer comprehensively. Do not summarize or truncate lists if the user asks for them.
- Naturally reference the document name and page number if using <CONTEXT_BLOCKS>, but do NOT mention "context blocks", "chunk IDs", or "relevance scores" in your output.
- Treat the <GLOBAL_SUMMARY> and <CONTEXT_BLOCKS> as your absolute ground truth.

FORMATTING RULES:
- BE VISUAL: If you are listing multiple items, requirements, tools, comparisons, or structured data, PROACTIVELY format them as a Markdown Table. Do not wait for the user to ask for a table.
- CODE: If you are outputting any code, JSON, or commands, ALWAYS wrap them in standard Markdown code blocks (```language) so they render correctly in the UI.
"""


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def route_query(query: str, chat_history: list[dict] | None = None, global_summary: str | None = None) -> dict:
    """
    The central intelligence router (Gatekeeper).
    """
    system_prompt = ROUTER_PROMPT
    if global_summary:
        system_prompt += f"\n\n--- GLOBAL DOCUMENT SUMMARY ---\n{global_summary}\n-------------------------------"

    messages = [{"role": "system", "content": system_prompt}]

    if chat_history:
        messages.extend(chat_history[-6:])

    messages.append({
        "role": "user",
        "content": f"Classify this message and respond with JSON only:\n\n{query}"
    })

    try:
        response = httpx.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.OPENROUTER_MODEL,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 1024,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
        raw_output = data["choices"][0]["message"]["content"].strip()

        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]

        result = json.loads(raw_output.strip())
        needs_search = result.get("needs_vector_search", True)
        
        final_result = {
            "needs_vector_search": bool(needs_search),
            "optimized_query": result.get("optimized_query") if needs_search else None,
            "response": result.get("response") if not needs_search else None
        }

        if final_result["needs_vector_search"] and not final_result["optimized_query"]:
            logger.warning("Router returned needs_vector_search=true without optimized_query — using raw query")
            final_result["optimized_query"] = query

        logger.info(
            f"[Gatekeeper] needs_search={final_result['needs_vector_search']} | "
            f"query='{query[:80]}'"
            + (f" | optimized='{final_result['optimized_query'][:80]}'" if final_result["needs_vector_search"] else "")
        )
        return final_result

    except json.JSONDecodeError as e:
        logger.error(f"[Gatekeeper] JSON parse error: {e} | raw_output='{raw_output[:200]}'")
        return {"needs_vector_search": True, "optimized_query": query}
    except Exception as e:
        logger.error(f"[Gatekeeper] Routing failed, defaulting to search: {e}")
        return {"needs_vector_search": True, "optimized_query": query}


def generate_answer(
    query: str,
    context: str,
    chat_history: list[dict] | None = None,
    global_summary: str | None = None,
) -> str:
    """
    Generate an answer using OpenRouter LLM strictly from provided context.
    """
    has_context = bool(context.strip())
    has_summary = bool(global_summary)
    has_history = bool(chat_history)

    if not has_context and not has_summary and not has_history:
        return "I couldn't find any relevant information in the documents. Could you try rephrasing your question or adjusting the search threshold to include more sources?"

    messages = [{"role": "system", "content": GENERATOR_PROMPT}]

    if chat_history:
        messages.extend(chat_history[-6:])

    user_content_parts = []

    if has_summary:
        user_content_parts.append(
            f"<GLOBAL_SUMMARY>\n{global_summary}\n</GLOBAL_SUMMARY>\n"
        )

    if has_context:
        user_content_parts.append(
            f"<CONTEXT_BLOCKS>\n{'=' * 60}\n{context}\n{'=' * 60}\n</CONTEXT_BLOCKS>\n"
        )
    else:
        if has_summary:
            user_content_parts.append(
                "<CONTEXT_BLOCKS>\nNo specific chunks were retrieved from the vector database for this query.\nPlease rely on the GLOBAL_SUMMARY above to answer the question.\n</CONTEXT_BLOCKS>\n"
            )
        else:
            user_content_parts.append(
                "<CONTEXT_BLOCKS>\nThis is a follow-up question. No new document chunks were retrieved.\nUse the conversation history above to answer the question accurately.\n</CONTEXT_BLOCKS>\n"
            )

    user_content_parts.append(f"\nQUESTION: {query}")
    messages.append({"role": "user", "content": "\n".join(user_content_parts)})

    try:
        response = httpx.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://docsinsightflow.app",
                "X-Title": "DocsInsightFlow",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.OPENROUTER_MODEL,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 1024,
                "top_p": 0.9,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()
        logger.info(f"[Generator] Generated answer ({len(answer)} chars)")
        return answer

    except Exception as e:
        logger.error(f"[Generator] LLM API error: {e}")
        return "Error generating response. Please try again later."


def execute_chat_pipeline(
    query: str,
    chat_history: list[dict],
    global_summary: str | None,
    chat_id: str,
    top_k: int,
    threshold: float,
    file_id: str | None
) -> tuple[str, list]:
    """
    Master orchestration function for the RAG pipeline.
    Returns: (final_answer_string, source_references_list)
    """
    logger.info(f"[Pipeline] Starting execution for query: '{query[:80]}'")
    
    # 1. Intent Routing (Gatekeeper)
    routing_result = route_query(query, chat_history, global_summary)
    needs_vector_search = routing_result.get("needs_vector_search", True)

    sources = []
    
    if needs_vector_search:
        search_query = routing_result.get("optimized_query") or query
        logger.info(f"[Pipeline] Vector search required | Optimized: '{search_query[:80]}'")
        
        # 2. RAG Retrieval
        try:
            sources = retrieve_relevant_chunks(
                chat_id=chat_id,
                query=search_query,
                top_k=top_k,
                threshold=threshold,
                file_id=file_id,
            )
        except Exception as e:
            logger.error(f"[Pipeline] Retrieval error: {e}")
            raise RuntimeError(f"Failed to retrieve documents: {e}")

        context = build_context_string(sources)

        # 3. Generate Answer (Second LLM Call)
        answer = generate_answer(
            query=query, 
            context=context, 
            chat_history=chat_history,
            global_summary=global_summary
        )
            
    else:
        # Zero-roundtrip response directly from the Gatekeeper LLM
        logger.info(f"[Pipeline] Vector search bypassed | Answer generated directly by Gatekeeper")
        answer = routing_result.get("response", "I could not generate a response based on the current context.")
        
    return answer, sources


def _build_generator_messages(
    query: str,
    context: str,
    chat_history: list[dict] | None,
    global_summary: str | None,
) -> list[dict]:
    """Build the message list for the generator LLM (shared by blocking and streaming paths)."""
    has_context = bool(context.strip())
    has_summary = bool(global_summary)

    messages = [{"role": "system", "content": GENERATOR_PROMPT}]
    if chat_history:
        messages.extend(chat_history[-6:])

    parts = []
    if has_summary:
        parts.append(f"<GLOBAL_SUMMARY>\n{global_summary}\n</GLOBAL_SUMMARY>\n")

    if has_context:
        parts.append(f"<CONTEXT_BLOCKS>\n{'=' * 60}\n{context}\n{'=' * 60}\n</CONTEXT_BLOCKS>\n")
    else:
        if has_summary:
            parts.append("<CONTEXT_BLOCKS>\nNo specific chunks were retrieved. Please rely on the GLOBAL_SUMMARY above.\n</CONTEXT_BLOCKS>\n")
        else:
            parts.append("<CONTEXT_BLOCKS>\nFollow-up question. No new chunks retrieved. Use the conversation history above.\n</CONTEXT_BLOCKS>\n")

    parts.append(f"\nQUESTION: {query}")
    messages.append({"role": "user", "content": "\n".join(parts)})
    return messages


def stream_generate_answer(
    query: str,
    context: str,
    chat_history: list[dict] | None = None,
    global_summary: str | None = None,
):
    """
    Generator that streams raw token strings from the OpenRouter LLM.
    Yields individual text chunks as they arrive.
    """
    messages = _build_generator_messages(query, context, chat_history, global_summary)

    with httpx.stream(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://docsinsightflow.app",
            "X-Title": "DocsInsightFlow",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.OPENROUTER_MODEL,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
            "top_p": 0.9,
            "stream": True,
        },
        timeout=60.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                payload = line[6:]
                try:
                    chunk = json.loads(payload)
                    text = chunk["choices"][0].get("delta", {}).get("content")
                    if text:
                        yield text
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def stream_chat_pipeline(
    query: str,
    chat_history: list[dict],
    global_summary: str | None,
    chat_id: str,
    top_k: int,
    threshold: float,
    file_id: str | None,
):
    """
    Master streaming orchestrator. Yields SSE-ready JSON strings.

    Event types:
      {"type": "status", "message": "..."}  — pipeline status update
      {"type": "token", "text": "..."}      — one LLM output token
      {"type": "done", "sources": [...]}    — completion signal with metadata
      {"type": "error", "message": "..."}   — something went wrong
    """
    import json as _json

    def emit(event: dict) -> str:
        return f"data: {_json.dumps(event)}\n\n"

    logger.info(f"[Stream] Starting pipeline for query: '{query[:80]}'")

    # ── 1. Gatekeeper ──────────────────────────────────────────────────────────
    routing_result = route_query(query, chat_history, global_summary)
    needs_vector_search = routing_result.get("needs_vector_search", True)

    sources = []
    context = ""

    if needs_vector_search:
        # ── 2. Status event ────────────────────────────────────────────────────
        yield emit({"type": "status", "message": "Searching your documents..."})

        search_query = routing_result.get("optimized_query") or query
        logger.info(f"[Stream] Vector search required | Optimized: '{search_query[:80]}'")

        try:
            sources = retrieve_relevant_chunks(
                chat_id=chat_id,
                query=search_query,
                top_k=top_k,
                threshold=threshold,
                file_id=file_id,
            )
        except Exception as e:
            logger.error(f"[Stream] Retrieval error: {e}")
            yield emit({"type": "error", "message": "Failed to search documents. Please try again."})
            return

        context = build_context_string(sources)
        if sources:
            yield emit({"type": "status", "message": f"Found {len(sources)} relevant section{'s' if len(sources) != 1 else ''}. Generating answer..."})

        # ── 3. Stream Generator LLM tokens ─────────────────────────────────────
        try:
            for token in stream_generate_answer(
                query=query,
                context=context,
                chat_history=chat_history,
                global_summary=global_summary,
            ):
                yield emit({"type": "token", "text": token})
        except Exception as e:
            logger.error(f"[Stream] Generator error: {e}")
            yield emit({"type": "error", "message": "Error generating response. Please try again."})
            return

    else:
        # ── Zero-roundtrip: stream the Gatekeeper's ready answer ───────────────
        logger.info("[Stream] Vector search bypassed | Streaming Gatekeeper response")
        direct_answer = routing_result.get("response", "I could not generate a response based on the current context.")
        # Emit in small chunks for a smooth streaming feel
        chunk_size = 4
        for i in range(0, len(direct_answer), chunk_size):
            yield emit({"type": "token", "text": direct_answer[i:i + chunk_size]})

    # ── 4. Done ────────────────────────────────────────────────────────────────
    serializable_sources = [
        {
            "file_id": s["file_id"],
            "file_name": s["file_name"],
            "page": s["page"],
            "score": s["score"],
            "excerpt": s.get("core_text", s["text"])[:300],
        }
        for s in sources
    ]
    yield emit({"type": "done", "sources": serializable_sources, "has_context": len(sources) > 0})
