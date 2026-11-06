from collections.abc import Iterable

from lawbot import config, expand, index, retrieve
from lawbot.models import Chunk


def search(question: str, k: int = config.TOP_K) -> list[Chunk]:
    found = retrieve.retrieve(question, k)
    added = expand.expand(question, found)
    unique: dict[str, Chunk] = {}
    for chunk in found + added:
        unique.setdefault(chunk.id, chunk)
    return list(unique.values())[: config.MAX_CHUNKS]


def get_chunks(ids: Iterable[str]) -> list[Chunk]:
    # Same order as ids; unknown ids are skipped.
    ids = list(ids)
    if not ids:
        return []
    stored = index.open_collection().get(ids=list(dict.fromkeys(ids)), include=["metadatas"])
    by_id = {chunk_id: metadata["chunk"] for chunk_id, metadata in zip(stored["ids"], stored["metadatas"])}
    return [index.chunk_from_json(by_id[chunk_id]) for chunk_id in ids if chunk_id in by_id]
