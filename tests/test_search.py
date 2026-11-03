import hashlib

import pytest

from lawbot import config, index, search
from lawbot.models import Chunk


def hashed_vector(text):
    digest = hashlib.sha256(text.encode()).digest()
    return [byte / 255 for byte in digest[:8]]


@pytest.fixture
def store_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(index, "CHUNKS_PATH", tmp_path / "chunks" / "chunks.jsonl")
    return tmp_path


def make_chunk(chunk_id, refs=()):
    return Chunk(chunk_id, "법", chunk_id, "", f"법 {chunk_id}", "20260101", "2026-11-02", refs, ("20270101",))


def store_with_vectors(monkeypatch, vectors, question_vector):
    chunks = [make_chunk(chunk_id) for chunk_id in vectors]
    index.store(chunks, list(vectors.values()))
    monkeypatch.setattr(index, "embed", lambda texts: [question_vector for _ in texts])
    return chunks


def test_index_rebuild_gives_same_chunks_file_and_collection(monkeypatch, store_dir):
    monkeypatch.setattr(index, "embed", lambda texts: [hashed_vector(text) for text in texts])

    assert index.main() == 0
    first = index.CHUNKS_PATH.read_bytes()
    assert index.main() == 0

    expected = index.build_chunks(config.RAW_DIR).chunks
    assert index.CHUNKS_PATH.read_bytes() == first
    assert b"\r" not in first
    assert [index.chunk_from_json(line) for line in first.decode().splitlines()] == expected
    assert index.open_collection().count() == len(expected)
    assert search.get_chunks(["근로기준법 제11조"]) == [c for c in expected if c.id == "근로기준법 제11조"]


def test_search_ranks_by_cosine_not_euclidean_distance(monkeypatch, store_dir):
    # "far" points the same way as the question but is ten times longer.
    store_with_vectors(monkeypatch, {"near": [0.5, 0.5], "far": [10.0, 1.0], "off": [0.0, 1.0]}, [1.0, 0.0])

    assert [chunk.id for chunk in search.search("질문", k=2)] == ["far", "near"]


def test_search_returns_whole_chunks_without_following_refs(monkeypatch, store_dir):
    chunks = [make_chunk("a", refs=("b",)), make_chunk("b")]
    index.store(chunks, [[1.0, 0.0], [0.0, 1.0]])
    monkeypatch.setattr(index, "embed", lambda texts: [[1.0, 0.0]])

    assert search.search("질문", k=1) == [chunks[0]]


def test_get_chunks_keeps_requested_order_and_skips_unknown_ids(monkeypatch, store_dir):
    chunks = store_with_vectors(monkeypatch, {"a": [1.0, 0.0], "b": [0.0, 1.0], "c": [1.0, 1.0]}, [1.0, 0.0])
    by_id = {chunk.id: chunk for chunk in chunks}

    assert search.get_chunks(["c", "없음", "a"]) == [by_id["c"], by_id["a"]]
    assert search.get_chunks([]) == []
