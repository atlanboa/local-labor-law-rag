import pytest

from lawbot import config, expand, index, retrieve, search
from lawbot.models import Chunk


def make_chunk(chunk_id, refs=()):
    return Chunk(chunk_id, "법", chunk_id, "", f"법 {chunk_id}", "20260101", "2026-11-02", refs)


@pytest.fixture
def stored(monkeypatch, tmp_path):
    # Real Chroma collection in tmp_path with fake vectors; no Ollama.
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(index, "CHUNKS_PATH", tmp_path / "chunks" / "chunks.jsonl")

    def store(chunks):
        index.store(chunks, [[1.0, float(n)] for n, _ in enumerate(chunks)])
        return {chunk.id: chunk for chunk in chunks}

    return store


def ids(chunks):
    return [chunk.id for chunk in chunks]


def test_follows_refs_of_top_found_chunk_in_stored_order(stored):
    by_id = stored([make_chunk("a", ("c", "b")), make_chunk("b"), make_chunk("c")])

    assert expand.expand("질문", [by_id["a"]]) == [by_id["c"], by_id["b"]]


def test_ignores_refs_of_lower_ranked_found_chunks(stored):
    by_id = stored([make_chunk("a"), make_chunk("b", ("c",)), make_chunk("c")])

    assert expand.expand("질문", [by_id["a"], by_id["b"]]) == []


def test_does_not_add_chunks_already_found_or_repeat_refs(stored):
    by_id = stored([make_chunk("a", ("b", "c", "c")), make_chunk("b"), make_chunk("c")])

    assert ids(expand.expand("질문", [by_id["a"], by_id["b"]])) == ["c"]


def test_skips_refs_missing_from_the_index(stored):
    by_id = stored([make_chunk("a", ("없음", "b")), make_chunk("b")])

    assert ids(expand.expand("질문", [by_id["a"]])) == ["b"]


def test_no_found_chunks_adds_nothing(stored):
    stored([make_chunk("a")])

    assert expand.expand("질문", []) == []


@pytest.mark.parametrize(
    "question",
    [
        "상시 근로자 4명인 사업장도 해고 예고가 적용되나요?",
        "상시 근로자 4명 이하 사업장에도 주휴일이 적용되나요?",
        "5인 미만 사업장도 연차가 있나요?",
        "직원이 3명뿐인 회사인데 퇴직금을 줘야 하나요?",
    ],
)
def test_small_workplace_questions_add_the_three_provisions(stored, question):
    stored([make_chunk(chunk_id) for chunk_id in expand.SMALL_WORKPLACE_IDS])

    assert ids(expand.expand(question, [])) == list(expand.SMALL_WORKPLACE_IDS)


@pytest.mark.parametrize(
    "question",
    [
        "상시 근로자 10명인 사업장도 취업규칙을 신고해야 하나요?",
        "5명 이하 사업장이 아니라 6명 사업장인데 어떻게 되나요?",
        "근로자가 4명이 모였는데 해고할 수 있나요?",
        "해고를 하려면 며칠 전에 예고해야 하나요?",
        "5인 이하 사업장에도 적용되나요?",
    ],
)
def test_other_questions_do_not_match_small_workplace_rule(question):
    assert not expand.is_small_workplace(question)


def test_small_workplace_provisions_come_first_and_skip_found(stored):
    chunks = [make_chunk("근로기준법 제11조"), make_chunk("근로기준법 시행령 제7조"), make_chunk("근로기준법 시행령 별표 1"), make_chunk("x", ("y",)), make_chunk("y")]
    by_id = stored(chunks)

    added = expand.expand("상시 근로자 4명 이하 사업장인데요", [by_id["x"], by_id["근로기준법 제11조"]])

    assert ids(added) == ["근로기준법 시행령 제7조", "근로기준법 시행령 별표 1", "y"]


def test_search_with_expand_appends_ref_after_found_and_respects_cap(monkeypatch, stored):
    by_id = stored([make_chunk("a", ("b",)), make_chunk("b"), make_chunk("c")])
    monkeypatch.setattr(retrieve, "retrieve", lambda question, k: [by_id["a"], by_id["c"]])

    monkeypatch.setattr(config, "MAX_CHUNKS", 3)
    assert ids(search.search("질문", k=2)) == ["a", "c", "b"]
    monkeypatch.setattr(config, "MAX_CHUNKS", 2)
    assert ids(search.search("질문", k=2)) == ["a", "c"]
