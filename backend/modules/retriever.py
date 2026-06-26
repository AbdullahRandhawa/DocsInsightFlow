from core.pinecone_client import query_vectors, fetch_vectors_by_ids
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
    Advanced RAG Retrieval with Context Window Expansion.

    Steps:
    1. Embed the (already optimized) query.
    2. Query Pinecone for top_k matches above the threshold.
    3. For each matching chunk, fetch its neighboring chunks (chunk_id - 1 and chunk_id + 1).
    4. Stitch the original chunk and its neighbors into one expanded context block.
    5. Return the expanded source list for the LLM.
    """
    top_k = top_k or settings.DEFAULT_TOP_K
    threshold = threshold if threshold is not None else settings.DEFAULT_THRESHOLD

    # Embed the optimized query
    query_vector = embed_query(query)

    # Build optional metadata filter (to restrict to a specific document)
    filter_dict = None
    if file_id:
        filter_dict = {"file_id": {"$eq": file_id}}

    # Query Pinecone for top matches
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

    # Filter by threshold score
    filtered = [m for m in raw_matches if m["score"] >= threshold]

    if not filtered:
        logger.info(f"No chunks above threshold {threshold} for query in chat '{chat_id}'")
        return []

    # ── Context Window Expansion ─────────────────────────────────────────
    # For each matched chunk, build the IDs of its left and right neighbors.
    # Vector ID format: "{file_id}_chunk_{chunk_id}"
    neighbor_ids_to_fetch = []
    for match in filtered:
        meta = match.get("metadata", {})
        fid = meta.get("file_id", "")
        cid = meta.get("chunk_id")
        if fid and cid is not None:
            for offset in [-1, 1]:
                neighbor_id = f"{fid}_chunk_{cid + offset}"
                neighbor_ids_to_fetch.append(neighbor_id)

    # Batch fetch all neighbors in one Pinecone request
    neighbor_map = fetch_vectors_by_ids(
        namespace=chat_id,
        ids=list(set(neighbor_ids_to_fetch)),
    )

    # Build expanded source list
    sources = []
    for match in filtered:
        meta = match.get("metadata", {})
        fid = meta.get("file_id", "")
        cid = meta.get("chunk_id", 0)
        core_text = meta.get("text", "")

        # Grab neighbor texts (if they exist)
        before_meta = neighbor_map.get(f"{fid}_chunk_{cid - 1}", {})
        after_meta = neighbor_map.get(f"{fid}_chunk_{cid + 1}", {})

        before_text = before_meta.get("text", "").strip()
        after_text = after_meta.get("text", "").strip()

        # Stitch: [before] + [core] + [after] into one seamless block
        expanded_parts = [p for p in [before_text, core_text, after_text] if p]
        expanded_text = " ".join(expanded_parts)

        sources.append(
            {
                "file_id": fid,
                "file_name": meta.get("file_name", "Unknown"),
                "page": meta.get("page", 0),
                "chunk_id": cid,
                "text": expanded_text,
                "core_text": core_text,   # Original match text (used for source excerpt display)
                "score": match["score"],
            }
        )

    logger.info(
        f"Retrieved {len(sources)} chunks with context expansion "
        f"(threshold={threshold}, top_k={top_k}, neighbors_fetched={len(neighbor_map)})"
    )
    return sources


def build_context_string(sources: list[dict]) -> str:
    """
    Build a formatted context string from expanded chunks for LLM injection.
    Each source block is clearly labeled with file name, page, and match score.
    """
    if not sources:
        return ""

    parts = []
    for i, source in enumerate(sources, 1):
        score_pct = round(source["score"] * 100)
        parts.append(
            f"[Context Block {i} | File: {source['file_name']} | Page: {source['page']} | Relevance: {score_pct}%]\n"
            f"{source['text']}"
        )

    return "\n\n---\n\n".join(parts)
