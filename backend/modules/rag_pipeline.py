import httpx
import json
import logging
from core.config import settings
from modules.retriever import retrieve_relevant_chunks, build_context_string

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# ROUTER PROMPT
# ──────────────────────────────────────────────────────────────────────────────
ROUTER_PROMPT = """SYSTEM: You are the first-response engine for DocsInsightFlow, a document intelligence SaaS.

Your job has TWO parts:
1. Generate a brief, engaging preliminary response to the user.
2. Decide if vector search is needed, and output a machine-readable decision.

You are provided with:
- Global Document Summary (high-level overview of the uploaded file)
- Chat History (recent conversation context)
- User's message
- Selected Document Name (if the user has clicked/filtered to a specific document, its name is shown here)

── PART 1: PRELIMINARY RESPONSE ──
Generate a brief preliminary response. This is NOT the final answer. It should:
- Acknowledge the user's query
- Provide 1-5 lines of relevant context from the Summary (if available and relevant)
- Signal your next action ("Let me search the documents for the exact details..." or "Let me check the document...")

EXAMPLES of good preliminary responses:
- "You're asking about the business model. From the summary, I can see the project uses a freemium model with subscription tiers for sellers. Let me search the document for the exact details on pricing..."
- "You want to know about the in-scope items. The summary mentions 7 deliverables including AI search and real-time chat. Let me find the specific breakdown in your document..."
- "Great question! Let me search your documents for information about [topic]..."

IMPORTANT RULES for preliminary response:
- DO NOT write a complete, detailed answer. Save the details for after the search.
- DO NOT list all items or explain in depth. Give just enough context to engage the user.
- If the Summary has relevant content: briefly reference it (1-4 lines) then say you'll search for specifics.
- If the Summary has no relevant content: simply acknowledge and say you'll search.
- If no Summary is provided at all (no document uploaded): say "Please upload a document so I can help you analyze it."
- Keep it to 1-5 lines max. Then append the routing decision.

── PART 2: ROUTING DECISION (machine block) ──
After your preliminary response (and ONLY after it), append this exact block:

---ROUTER_DECISION---
{"needs_vector_search": true/false, "optimized_query": "..."}
---END_ROUTER_DECISION---

DECISION RULES:
- SET "needs_vector_search" TO false ONLY IF the user is:
  * Making small talk, greeting, saying thanks
  * Asking meta-questions about the app itself ("what can you do?", "how do you work?")
  * Asking for a joke, code help, or general advice unrelated to documents
  * Asking you to elaborate on something just discussed in chat history (follow-up, no new info needed)
  * If no Global Summary is provided (no document uploaded) — also set to false, preliminary response should tell user to upload

- SET "needs_vector_search" TO true for EVERYTHING else:
  * Any question about the uploaded documents
  * Specific facts, metrics, names, architecture, rules, data points
  * Comparisons, lists, or details that need precise document context
  * When in doubt, ALWAYS default to true

QUERY REWRITING (only when needs_vector_search is true):
- Strip conversational fluff
- Resolve pronouns using Chat History
- Preserve technical proper nouns exactly

CRITICAL OUTPUT RULES:
- The preliminary response MUST come FIRST (natural text)
- The ---ROUTER_DECISION--- block MUST come LAST
- The JSON inside the block must be valid, parseable JSON
- Do NOT include any text after the ---END_ROUTER_DECISION--- marker
"""

# ──────────────────────────────────────────────────────────────────────────────
# GENERATOR PROMPT
# ──────────────────────────────────────────────────────────────────────────────
GENERATOR_PROMPT = """You are DocsInsightFlow — a document intelligence assistant.
Your purpose: Analyze uploaded documents (PDFs, DOCX, text) and answer questions about their content.
Your capabilities: Semantic search across documents, cross-document synthesis, page-level citations, sentiment analysis.
Your limitations: You can only answer based on the documents provided.

You will receive:
1. <GLOBAL_SUMMARY>: A structured overview of the document(s). May be empty if no document is uploaded.
2. <CONTEXT_BLOCKS>: Specific excerpts retrieved via vector search. May be empty.
3. Chat History: Recent conversational context.
4. The PRELIMINARY RESPONSE (the brief overview that was already shown to the user)

IMPORTANT CONTEXT:
- The user has already seen a brief preliminary response (1-5 lines) based on the summary.
- Your job is to provide the DETAILED, SPECIFIC answer using the context blocks.
- DO NOT re-introduce or repeat what was already said in the preliminary response.
- Start directly with new, deeper details from the context blocks.

NO-DOCUMENT HANDLING:
- If no Global Summary and no Context Blocks are provided: there is no document uploaded.
- In this case, if the user is asking about documents, respond: "It looks like you haven't uploaded a document yet. Please upload a PDF, DOCX, or text file, and I'll be happy to help you analyze it!"
- If the user is asking a general question (greeting, coding help, etc.), answer helpfully using your general knowledge, then add a brief reminder about your document-analysis purpose.

GENERAL KNOWLEDGE CLAUSE:
- If the user's message is a general question (greeting, coding help, conceptual question) with no connection to documents, answer helpfully using your general knowledge.
- [IMPORTENT]: After giving the answer, add a short reminder like: "By the way, my core purpose is to help you analyze and extract insights from your uploaded documents. Feel free to ask me anything about them!"
- Never refuse a general question. Be helpful first, then redirect.

YOUR ANALYSIS PROCESS:
1. DEEP SEARCH: Read every word of <CONTEXT_BLOCKS> and <GLOBAL_SUMMARY>. Look for synonyms, related concepts, partial matches.
2. SYNTHESIZE: Combine info from multiple blocks. Extract every item if the user asks for a list.
3. FALLBACK: Only if the answer is truly 100% missing, politely inform the user and suggest rephrasing.

STRICT RULES:
- Rely strictly on provided context. Do NOT invent facts.
- Answer comprehensively. Do not truncate lists.
- Naturally reference document name and page if using <CONTEXT_BLOCKS>, but never mention "context blocks", "chunk IDs", or "relevance scores".
- Treat <GLOBAL_SUMMARY> and <CONTEXT_BLOCKS> as ground truth.

FORMATTING RULES:
- BE VISUAL: Use Markdown Tables for lists, comparisons, or structured data.
- CODE: Wrap code, JSON, or commands in ```language blocks.
"""


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def route_query(query: str, chat_history: list[dict] | None = None, global_summary: str | None = None, selected_file_name: str | None = None) -> dict:
    """
    The central intelligence router (Gatekeeper) — blocking version.
    Used by execute_chat_pipeline() for non-streaming path.
    """
    system_prompt = ROUTER_PROMPT
    if global_summary:
        system_prompt += f"\n\n--- GLOBAL DOCUMENT SUMMARY ---\n{global_summary}\n-------------------------------"
    if selected_file_name:
        system_prompt += f"\n\n--- SELECTED DOCUMENT ---\nThe user has selected/filtered to this specific document: {selected_file_name}\nOnly answer about this document.\n-------------------------------"

    messages = [{"role": "system", "content": system_prompt}]

    if chat_history:
        messages.extend(chat_history[-6:])

    messages.append({
        "role": "user",
        "content": query
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

        # Extract the JSON decision block
        decision = _extract_router_decision(raw_output)
        if decision:
            return decision

        # Fallback: try parsing entire output as JSON (backward compat)
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


def _extract_router_decision(raw_text: str) -> dict | None:
    """
    Extract the routing decision JSON from the ---ROUTER_DECISION--- block.
    Returns None if the marker is not found.
    """
    marker_start = "---ROUTER_DECISION---"
    marker_end = "---END_ROUTER_DECISION---"

    start_idx = raw_text.find(marker_start)
    end_idx = raw_text.find(marker_end)

    if start_idx != -1 and end_idx != -1:
        json_str = raw_text[start_idx + len(marker_start):end_idx].strip()
        try:
            result = json.loads(json_str)
            needs_search = result.get("needs_vector_search", True)
            return {
                "needs_vector_search": bool(needs_search),
                "optimized_query": result.get("optimized_query") if needs_search else None,
                "response": result.get("response") if not needs_search else None,
                "_preliminary": raw_text[:start_idx].strip()
            }
        except json.JSONDecodeError:
            logger.warning(f"[Router] Found marker but JSON parse failed: {json_str[:100]}")
            return None

    return None


def stream_router_response(
    query: str,
    chat_history: list[dict] | None = None,
    global_summary: str | None = None,
    selected_file_name: str | None = None,
):
    """
    Streaming router that:
    1. Yields preliminary response tokens immediately (engages the user)
    2. Detects the ---ROUTER_DECISION--- marker mid-stream
    3. Yields a special dict {'__ROUTER_DECISION__': {...}} as the final item

    Usage:
        for item in stream_router_response(query, chat_history, summary):
            if isinstance(item, dict) and '__ROUTER_DECISION__' in item:
                decision = item['__ROUTER_DECISION__']
                break
            # item is a text token — stream to frontend
            yield item
    """
    system_prompt = ROUTER_PROMPT
    if global_summary:
        system_prompt += f"\n\n--- GLOBAL DOCUMENT SUMMARY ---\n{global_summary}\n-------------------------------"
    if selected_file_name:
        system_prompt += f"\n\n--- SELECTED DOCUMENT ---\nThe user has selected/filtered to this specific document: {selected_file_name}\nOnly answer about this document.\n-------------------------------"

    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history[-6:])
    messages.append({"role": "user", "content": query})

    MARKER = "---ROUTER_DECISION---"
    SAFE_WINDOW = len(MARKER)  # 20 chars — rolling buffer size

    buffer = ""
    past_marker = False
    decision_buffer = ""

    try:
        with httpx.stream(
            method="POST",
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
                "stream": True,
            },
            timeout=15.0,
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
                        if not text:
                            continue
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

                    if past_marker:
                        decision_buffer += text
                    else:
                        buffer += text
                        # Check if marker appeared in the buffer
                        marker_pos = buffer.find(MARKER)
                        if marker_pos != -1:
                            # Yield any remaining preliminary text before the marker
                            pre = buffer[:marker_pos]
                            if pre:
                                yield pre
                            # Switch to decision-buffering mode
                            past_marker = True
                            decision_buffer = buffer[marker_pos + len(MARKER):]
                        else:
                            # Safe to yield the oldest part of the buffer
                            if len(buffer) > SAFE_WINDOW:
                                safe_end = len(buffer) - SAFE_WINDOW
                                yield buffer[:safe_end]
                                buffer = buffer[safe_end:]

    except Exception as e:
        logger.error(f"[StreamRouter] API error: {e}")
        # Yield whatever we have as preliminary, then default decision
        if buffer:
            yield buffer
        yield {"__ROUTER_DECISION__": {"needs_vector_search": True, "optimized_query": query}}
        return

    # Parse the decision from the buffered text after the marker
    end_marker = "---END_ROUTER_DECISION---"
    end_pos = decision_buffer.find(end_marker)

    if end_pos != -1:
        json_str = decision_buffer[:end_pos].strip()
        try:
            result = json.loads(json_str)
            needs_search = result.get("needs_vector_search", True)
            decision = {
                "needs_vector_search": bool(needs_search),
                "optimized_query": result.get("optimized_query") if needs_search else None,
                "response": result.get("response") if not needs_search else None,
            }
            logger.info(
                f"[StreamRouter] needs_search={decision['needs_vector_search']} | "
                f"query='{query[:80]}'"
                + (f" | optimized='{decision['optimized_query'][:80]}'" if decision['needs_vector_search'] else "")
            )
            yield {"__ROUTER_DECISION__": decision}
            return
        except json.JSONDecodeError as e:
            logger.error(f"[StreamRouter] JSON parse error in decision block: {e} | json='{json_str[:200]}'")

    # Fallback: default to search
    logger.warning("[StreamRouter] No valid decision found, defaulting to search")
    yield {"__ROUTER_DECISION__": {"needs_vector_search": True, "optimized_query": query}}


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
                "<CONTEXT_BLOCKS>\nNo document is uploaded. No chunks were retrieved.\n</CONTEXT_BLOCKS>\n"
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
    file_id: str | None,
    selected_file_name: str | None = None,
) -> tuple[str, list]:
    """
    Master orchestration function for the RAG pipeline (blocking).
    Returns: (final_answer_string, source_references_list)
    """
    logger.info(f"[Pipeline] Starting execution for query: '{query[:80]}'")
    
    # 1. Intent Routing (Gatekeeper)
    routing_result = route_query(query, chat_history, global_summary, selected_file_name)
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
        # Use preliminary response if available, otherwise fallback
        answer = routing_result.get("_preliminary") or routing_result.get("response", "I could not generate a response based on the current context.")
        
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
            parts.append("<CONTEXT_BLOCKS>\nNo document uploaded. No chunks retrieved.\n</CONTEXT_BLOCKS>\n")

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
    selected_file_name: str | None = None,
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

    # Emit an immediate status to assure the user the backend is processing
    yield emit({"type": "status", "message": "Analyzing query..."})

    # ── 1. Stream Router (Gatekeeper) — yields tokens immediately ──────────────
    #    The router streams a preliminary response while simultaneously deciding
    #    if vector search is needed. The decision comes as the last item.
    routing_decision = None
    router_streamed_something = False

    for item in stream_router_response(query, chat_history, global_summary):
        if isinstance(item, dict) and "__ROUTER_DECISION__" in item:
            routing_decision = item["__ROUTER_DECISION__"]
            break
        # Regular text token — stream to frontend immediately
        router_streamed_something = True
        yield emit({"type": "token", "text": item})

    if routing_decision is None:
        routing_decision = {"needs_vector_search": True, "optimized_query": query}

    needs_vector_search = routing_decision.get("needs_vector_search", True)
    sources = []
    context = ""

    # If no document uploaded (no global_summary) and needs_vector_search is true,
    # we can't search. Override to false and provide guidance.
    if needs_vector_search and not global_summary:
        logger.info("[Stream] No document uploaded — skipping search, telling user to upload")
        yield emit({"type": "status", "message": "No document found. Please upload a document first."})
        # If router didn't stream anything, provide a fallback message
        if not router_streamed_something:
            yield emit({"type": "token", "text": "Please upload a document so I can help you analyze it."})
        yield emit({"type": "done", "sources": [], "has_context": False})
        return

    if needs_vector_search:
        # ── 2. Status event ────────────────────────────────────────────────────
        yield emit({"type": "status", "message": "Searching your documents..."})

        search_query = routing_decision.get("optimized_query") or query
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

        # ── 3. Stream Generator LLM tokens (seamless continuation) ─────────────
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
        # ── No search needed — router already streamed the preliminary answer ──
        logger.info("[Stream] Vector search bypassed | Router streamed the answer")
        # If router didn't stream anything (edge case), use the response field
        if not router_streamed_something:
            direct_answer = routing_decision.get("response", "")
            if direct_answer:
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