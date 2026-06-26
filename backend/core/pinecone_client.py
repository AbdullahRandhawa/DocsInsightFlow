from pinecone import Pinecone, ServerlessSpec
from core.config import settings
import logging

logger = logging.getLogger(__name__)

_pinecone_client: Pinecone | None = None
_index = None


def init_pinecone() -> None:
    """Initialize Pinecone client and ensure index exists."""
    global _pinecone_client, _index
    if _pinecone_client is not None:
        return

    try:
        _pinecone_client = Pinecone(api_key=settings.PINECONE_API_KEY)

        existing_indexes = [i.name for i in _pinecone_client.list_indexes()]
        if settings.PINECONE_INDEX_NAME not in existing_indexes:
            logger.info(f"Creating Pinecone index: {settings.PINECONE_INDEX_NAME}")
            _pinecone_client.create_index(
                name=settings.PINECONE_INDEX_NAME,
                dimension=settings.EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            logger.info("Pinecone index created")
        else:
            logger.info(f"Pinecone index '{settings.PINECONE_INDEX_NAME}' already exists")

        _index = _pinecone_client.Index(settings.PINECONE_INDEX_NAME)
        logger.info("Pinecone client initialized")
    except Exception as e:
        logger.error(f"Pinecone initialization failed: {e}")
        raise


def get_index():
    """Return the Pinecone Index object."""
    if _index is None:
        raise RuntimeError("Pinecone not initialized. Call init_pinecone() first.")
    return _index


def upsert_vectors(
    namespace: str,
    vectors: list[dict],
    batch_size: int = 100,
) -> int:
    """
    Upsert vectors to Pinecone in batches.
    Each vector dict: {"id": str, "values": list[float], "metadata": dict}
    Returns total upserted count.
    """
    index = get_index()
    total = 0
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i : i + batch_size]
        index.upsert(vectors=batch, namespace=namespace)
        total += len(batch)
    logger.info(f"Upserted {total} vectors to namespace '{namespace}'")
    return total


def query_vectors(
    namespace: str,
    query_vector: list[float],
    top_k: int = 5,
    filter_dict: dict | None = None,
) -> list[dict]:
    """
    Query Pinecone for nearest neighbors.
    Returns list of matches with id, score, metadata.
    """
    index = get_index()
    kwargs = {
        "vector": query_vector,
        "top_k": top_k,
        "namespace": namespace,
        "include_metadata": True,
    }
    if filter_dict:
        kwargs["filter"] = filter_dict

    response = index.query(**kwargs)
    return [
        {
            "id": match.id,
            "score": round(match.score, 4),
            "metadata": match.metadata,
        }
        for match in response.matches
    ]


def delete_namespace(namespace: str) -> None:
    """Delete all vectors in a namespace (used when deleting a chat)."""
    index = get_index()
    index.delete(delete_all=True, namespace=namespace)
    logger.info(f"Deleted all vectors in namespace '{namespace}'")


def fetch_vectors_by_ids(namespace: str, ids: list[str]) -> dict[str, dict]:
    """
    Fetch specific vectors by their IDs (used for context window expansion).
    Returns a dict of {id: metadata}.
    """
    index = get_index()
    if not ids:
        return {}
    try:
        response = index.fetch(ids=ids, namespace=namespace)
        result = {}
        for vid, vec in response.vectors.items():
            result[vid] = vec.metadata or {}
        return result
    except Exception as e:
        logger.warning(f"fetch_vectors_by_ids failed: {e}")
        return {}


def delete_vectors_by_filter(namespace: str, filter_dict: dict) -> None:
    """Delete vectors matching a metadata filter (used when removing a document)."""
    index = get_index()
    index.delete(filter=filter_dict, namespace=namespace)
    logger.info(f"Deleted vectors with filter {filter_dict} in namespace '{namespace}'")
