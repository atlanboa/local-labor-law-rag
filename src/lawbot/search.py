from collections.abc import Iterable

from lawbot import index
from lawbot.models import Chunk


def search(question: str, k: int = 5) -> list[Chunk]:
    (vector,) = index.embed([question])
    result = index.open_collection().query(query_embeddings=[vector], n_results=k, include=["metadatas"])
    return [index.chunk_from_json(metadata["chunk"]) for metadata in result["metadatas"][0]]


def get_chunks(ids: Iterable[str]) -> list[Chunk]:
    # Same order as ids; unknown ids are skipped.
    ids = list(ids)
    if not ids:
        return []
    stored = index.open_collection().get(ids=list(dict.fromkeys(ids)), include=["metadatas"])
    by_id = {chunk_id: metadata["chunk"] for chunk_id, metadata in zip(stored["ids"], stored["metadatas"])}
    return [index.chunk_from_json(by_id[chunk_id]) for chunk_id in ids if chunk_id in by_id]
