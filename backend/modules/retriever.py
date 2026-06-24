from core.pinecone_client import query_vectors
from modules.embeddings import embed_query
from core.config import settings
import logging

logger = logging.getLogger(__name__)


def retrieve_relevant_chunks(
    chat_id: str,
    query: str,
    top_k: int | None = None,
    threshold: float | None = None,
    file_id: str | None = None,
) -> list[dict]:
    """
    Retrieve relevant chunks from Pinecone for a given query.

    Args:
        chat_id: Pinecone namespace (= chat_id)
        query: User query string
        top_k: Number of results to retrieve (default from settings)
        threshold: Minimum cosine similarity score (default from settings)
        file_id: Optional filter to restrict retrieval to one document

    Returns:
        List of source dicts with keys:
          file_id, file_name, page, chunk_id, text, score
    """
    top_k = top_k or settings.DEFAULT_TOP_K
    threshold = threshold if threshold is not None else settings.DEFAULT_THRESHOLD

    # Embed the query
    query_vector = embed_query(query)

    # Build optional metadata filter
    filter_dict = None
    if file_id:
        filter_dict = {"file_id": {"$eq": file_id}}

    # Query Pinecone
    try:
        raw_matches = query_vectors(
            namespace=chat_id,
            query_vector=query_vector,
            top_k=top_k,
            filter_dict=filter_dict,
        )
    except Exception as e:
        logger.error(f"Pinecone query failed: {e}")
        raise RuntimeError(f"Vector database query failed: {e}")

    # Filter by threshold
    filtered = [m for m in raw_matches if m["score"] >= threshold]

    if not filtered:
        logger.info(
            f"No chunks above threshold {threshold} for query in chat '{chat_id}'"
        )
        return []

    # Format results
    sources = []
    for match in filtered:
        meta = match.get("metadata", {})
        sources.append(
            {
                "file_id": meta.get("file_id", ""),
                "file_name": meta.get("file_name", "Unknown"),
                "page": meta.get("page", 0),
                "chunk_id": meta.get("chunk_id", 0),
                "text": meta.get("text", ""),
                "score": match["score"],
            }
        )

    logger.info(f"Retrieved {len(sources)} chunks (threshold={threshold}, top_k={top_k})")
    return sources


def build_context_string(sources: list[dict]) -> str:
    """
    Build a formatted context string from retrieved chunks
    for injection into the LLM prompt.
    """
    if not sources:
        return ""

    parts = []
    for i, source in enumerate(sources, 1):
        parts.append(
            f"[Source {i}: {source['file_name']}, Page {source['page']}]\n"
            f"{source['text']}"
        )

    return "\n\n---\n\n".join(parts)
