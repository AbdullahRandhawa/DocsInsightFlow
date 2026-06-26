import httpx
from core.config import settings
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DocsInsightFlow, an intelligent document analysis assistant.

You will be provided with:
1. A <GLOBAL_SUMMARY> of the document(s)
2. Specific <CONTEXT_BLOCKS> retrieved via vector search
3. The recent Chat History

YOUR PROCESS (follow this in order):
1. EVALUATE the context blocks, the global summary, and the chat history to see if they contain the answer to the user's question.
2. SYNTHESIZE a clear, complete answer using this combined knowledge.
3. If the answer is completely unavailable in the summary, context blocks, or chat history, respond with EXACTLY: "The answer is not available in the provided documents."

STRICT RULES:
- You may use the global summary, the context blocks, AND the chat history to synthesize your answer.
- Do NOT fabricate facts, statistics, or citations not present in the provided information.
- Be concise and factual. You may naturally reference the source document and page when using context blocks.
- Do NOT mention the context block numbers or relevance scores in your answer."""


def generate_answer(
    query: str,
    context: str,
    chat_history: list[dict] | None = None,
    global_summary: str | None = None,
) -> str:
    """
    Generate an answer using OpenRouter LLM strictly from provided context.

    Args:
        query: The user's question
        context: Retrieved document chunks as formatted string
        chat_history: Optional list of prior {role, content} messages for session memory

    Returns:
        Generated answer string
    """
    # Only bail if we have absolutely nothing — no chunks AND no summary
    has_context = bool(context.strip())
    has_summary = bool(global_summary)

    if not has_context and not has_summary:
        return "The answer is not available in the provided document."

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject limited chat history for session memory (last 6 exchanges)
    if chat_history:
        recent_history = chat_history[-6:]
        messages.extend(recent_history)

    # Inject context + query
    user_content_parts = []

    if has_summary:
        user_content_parts.append(
            f"<GLOBAL_SUMMARY>\n"
            f"{global_summary}\n"
            f"</GLOBAL_SUMMARY>\n"
        )

    if has_context:
        user_content_parts.append(
            f"<CONTEXT_BLOCKS>\n"
            f"{'=' * 60}\n"
            f"{context}\n"
            f"{'=' * 60}\n"
            f"</CONTEXT_BLOCKS>\n"
        )
    else:
        # No vector chunks matched — tell the LLM explicitly so it relies on the summary
        user_content_parts.append(
            "<CONTEXT_BLOCKS>\n"
            "No specific chunks were retrieved from the vector database for this query.\n"
            "Please rely on the GLOBAL_SUMMARY above to answer the question.\n"
            "</CONTEXT_BLOCKS>\n"
        )

    user_content_parts.append(f"\nQUESTION: {query}")

    messages.append({"role": "user", "content": "\n".join(user_content_parts)})

    logger.info("================== LLM PROMPT PAYLOAD ==================")
    import json
    logger.info(json.dumps(messages, indent=2))
    logger.info("========================================================")

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
                "temperature": 0.1,       # Low temp for factual, consistent answers
                "max_tokens": 1024,
                "top_p": 0.9,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()
        logger.info(f"Generated answer ({len(answer)} chars) for query: {query[:60]}...")
        return answer

    except httpx.HTTPStatusError as e:
        logger.error(f"OpenRouter HTTP error: {e.response.status_code} - {e.response.text}")
        raise RuntimeError(f"LLM API error: {e.response.status_code}")
    except httpx.TimeoutException:
        logger.error("OpenRouter request timed out")
        return "Error generating response. Please try again later."


def generate_document_summary(text: str) -> str:
    """
    Generate a comprehensive summary of a document's extracted text.
    Used during background upload processing.
    """
    if not text.strip():
        return "No extractable text to summarize."

    prompt = (
        "You are an expert document summarizer. Please write a comprehensive, "
        "detailed summary of the following document text. Capture the main purpose, "
        "key topics, and any important conclusions.\n\n"
        f"DOCUMENT TEXT:\n{text}"
    )

    try:
        response = httpx.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 1500,
            },
            timeout=45.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        return "Summary could not be generated at this time."


def generate_chat_title(first_message: str) -> str:
    """
    Auto-generate a short chat title from the user's first message.
    Falls back to a truncated version of the message if LLM fails.
    """
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
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Generate a very short title (3-5 words max) for a chat "
                            f"that starts with this question. Return ONLY the title, no punctuation:\n\n"
                            f"{first_message}"
                        ),
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 20,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        title = response.json()["choices"][0]["message"]["content"].strip()
        return title[:60]  # cap at 60 chars
    except Exception:
        # Fallback: truncate the message
        return first_message[:50].strip() + ("..." if len(first_message) > 50 else "")
