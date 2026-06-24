import httpx
from core.config import settings
import logging

logger = logging.getLogger(__name__)


def load_model() -> None:
    """No-op now that embeddings are computed via OpenRouter API."""
    pass


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using OpenRouter API.
    """
    if not texts:
        return []

    try:
        response = httpx.post(
            url="https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.EMBEDDING_MODEL,
                "input": texts,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        
        # Sort embeddings by their index in the response list to ensure order matching
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise RuntimeError(f"Embedding generation failed: {e}")


def embed_query(query: str) -> list[float]:
    """Generate embedding for a single query string."""
    embeddings = embed_texts([query])
    if not embeddings:
        raise RuntimeError("No embedding returned for query")
    return embeddings[0]
