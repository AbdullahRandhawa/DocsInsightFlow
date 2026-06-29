import httpx
from core.config import settings
import logging

logger = logging.getLogger(__name__)

def generate_document_summary(text: str) -> str:
    """
    Generate a comprehensive summary of a document's extracted text.
    Used during background upload processing.
    """
    if not text.strip():
        return "No extractable text to summarize."

    prompt = (
        "You are an expert document summarizer. Write a concise, high-level summary "
        "of the following document text (2-3 paragraphs max). Capture the main purpose, "
        "key topics, and core message. Do not extract exhaustive details or lists.\n\n"
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
                "max_tokens": 500,
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
