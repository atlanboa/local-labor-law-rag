from fastapi.testclient import TestClient

from lawbot import server
from lawbot.answer import ChatStats
from lawbot.models import Chunk


def chunk(article: str, pending: tuple[str, ...] = ()) -> Chunk:
    return Chunk(
        id=f"근로기준법 {article}",
        law="근로기준법",
        article=article,
        title="제목",
        text=f"근로기준법 {article} 본문",
        effective_date="20251023",
        collected_at="20261102",
        pending_effective_dates=pending,
    )


def test_ask_returns_reply_and_only_cited_chunks(monkeypatch):
    chunks = [chunk("제26조"), chunk("제27조", ("20261208",))]
    monkeypatch.setattr(server, "search", lambda question, k: chunks)
    monkeypatch.setattr(server, "generate", lambda question, found: ("답 [2]", [2], ChatStats(1.234, 900)))

    body = TestClient(server.app).post("/api/ask", json={"question": "해고 예고는?"}).json()

    assert body["reply"] == "답 [2]"
    assert [c["id"] for c in body["citations"]] == ["근로기준법 제27조"]
    assert body["citations"][0]["number"] == 2
    assert body["citations"][0]["effective_date"] == "2025-10-23"
    assert body["citations"][0]["pending_effective_dates"] == ["2026-12-08"]
    assert body["retrieved"] == ["근로기준법 제26조", "근로기준법 제27조"]
    assert body["seconds"] == 1.2


def test_ask_without_chunks_skips_the_model(monkeypatch):
    monkeypatch.setattr(server, "search", lambda question, k: [])
    monkeypatch.setattr(server, "generate", lambda *args: (_ for _ in ()).throw(AssertionError("called")))

    body = TestClient(server.app).post("/api/ask", json={"question": "세율은?"}).json()

    assert body["citations"] == []
    assert body["seconds"] is None


def test_ask_rejects_empty_question():
    response = TestClient(server.app).post("/api/ask", json={"question": ""})
    assert response.status_code == 422
