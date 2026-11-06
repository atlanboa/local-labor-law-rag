from lawbot import index
from lawbot.models import Chunk


def retrieve(question: str, k: int) -> list[Chunk]:
    # Most relevant first.
    (vector,) = index.embed([question])
    result = index.open_collection().query(query_embeddings=[vector], n_results=k, include=["metadatas"])
    return [index.chunk_from_json(metadata["chunk"]) for metadata in result["metadatas"][0]]
