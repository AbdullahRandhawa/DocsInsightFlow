import httpx
import json
import logging
from core.config import settings

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """You are the core intelligence router for DocsInsightFlow, a document analysis assistant.
Your job is to analyze the user's latest message and the chat history, and determine the intent.

You MUST respond with a valid JSON object matching exactly one of these two structures:

1. If the user is asking a general conversation question, greeting, or chitchat (e.g. "Hi", "Who are you?", "Thanks"):
{
    "type": "chat",
    "response": "Your friendly, helpful conversational response. Keep it brief and remind them you are here to analyze their uploaded documents."
}

2. If the user is asking a question that requires searching for specific facts in their uploaded documents (e.g. "What is X?", "Why did it fail?"):
{
    "type": "search",
    "optimized_query": "The rewritten, standalone search query that incorporates context from the chat history so it can be perfectly embedded for vector search. Resolve all pronouns and vague references."
}

3. If the user is asking for a global summary, overview, or general explanation of what the document is about (e.g. "Summarize this file", "What is this document about?", "Give me an overview"):
{
    "type": "summary"
}

Always output raw JSON only. Do not wrap in markdown code blocks.
"""


def route_query(query: str, chat_history: list[dict] | None = None) -> dict:
    """
    Single LLM call that:
    1. Classifies intent (chitchat vs document search)
    2. If search: rewrites the query into a clean, standalone, optimized search query
    3. If chitchat: returns a direct friendly response

    Falls back to a raw search with the original query if anything fails.
    """
    messages = [{"role": "system", "content": ROUTER_PROMPT}]

    # Pass recent history so the LLM can resolve pronouns and references
    if chat_history:
        messages.extend(chat_history[-4:])

    messages.append({"role": "user", "content": f"User's new message: {query}"})

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
                "temperature": 0.1,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
        raw_output = data["choices"][0]["message"]["content"].strip()

        # Strip markdown code block wrappers if model added them
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]
        if raw_output.startswith("```"):
            raw_output = raw_output[3:]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]

        result = json.loads(raw_output.strip())

        if "type" not in result:
            raise ValueError("Missing 'type' in router response")

        logger.info(f"Router decision: type={result.get('type')}, query='{query[:60]}'")
        return result

    except Exception as e:
        logger.error(f"Routing failed, defaulting to search: {e}")
        # Failsafe: if anything breaks, default to a search with the raw query
        return {
            "type": "search",
            "optimized_query": query,
        }
