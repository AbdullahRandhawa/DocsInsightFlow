import httpx
from core.config import settings
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DocsInsightFlow, a precise document question-answering assistant.

STRICT RULES:
1. Answer ONLY using the provided document context below.
2. Do NOT use any prior knowledge, assumptions, or information outside the context.
3. If the answer cannot be found in the context, respond with EXACTLY:
   "The answer is not available in the provided document."
4. Always be concise and factual.
5. When referencing information, you may mention the source document and page naturally in your answer.
6. Do not fabricate citations, statistics, or facts not present in the context."""


def generate_answer(
    query: str,
    context: str,
    chat_history: list[dict] | None = None,
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
    if not context.strip():
        return "The answer is not available in the provided document."

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject limited chat history for session memory (last 6 exchanges)
    if chat_history:
        recent_history = chat_history[-6:]
        messages.extend(recent_history)

    # Inject context + query
    user_content = (
        f"DOCUMENT CONTEXT:\n"
        f"{'=' * 60}\n"
        f"{context}\n"
        f"{'=' * 60}\n\n"
        f"QUESTION: {query}"
    )
    messages.append({"role": "user", "content": user_content})

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
        raise RuntimeError("LLM request timed out. Please try again.")
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        raise RuntimeError(f"Answer generation failed: {e}")


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
