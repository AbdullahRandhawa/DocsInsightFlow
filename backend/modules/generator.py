import httpx
import asyncio
from core.config import settings
import logging

logger = logging.getLogger(__name__)

# Maximum chars of raw text to send to LLM for summary (~3000 words ≈ 15000 chars)
MAX_SUMMARY_INPUT_CHARS = 15000

async def generate_document_summary(text: str) -> str:
    """
    Generate a fast, structured summary of a document's extracted text.
    Accepts raw extracted text (not chunks). First 3000 words are used.
    Returns ~400 words max. No reasoning — direct output only.
    Used during background upload processing.
    """
    if not text.strip():
        return "No extractable text to summarize."

    # Truncate to first 3000 words (~15000 chars)
    truncated = text[:MAX_SUMMARY_INPUT_CHARS]

    prompt = (
        "Summarize the following document in ~400 words maximum.\n"
        "Output ONLY the summary — no reasoning, no explanation, no introductory phrases.\n\n"
        "Structure the summary as:\n\n"
        "DOCUMENT OVERVIEW: Describe what this document is about comprehensively — "
        "the main subject, purpose, scope, and what makes it important or notable. "
        "This should be a proper overview, not just 1-2 lines.\n\n"
        "KEY FACTS & FIGURES:\n"
        "- [Bullet point each important fact, statistic, date, name, or figure]\n\n"
        "SECTION BREAKDOWN:\n"
        "- [For each major section/chapter/paragraph theme: 2-4 line summary of its core points]\n\n"
        f"DOCUMENT TEXT:\n{truncated}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
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
