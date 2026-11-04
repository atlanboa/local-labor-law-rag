import json

import httpx
import pytest

from lawbot import answer as answer_module
from lawbot import cli, config
from lawbot.models import Chunk


class FakeOllama:
    def __init__(self):
        self.prompts = []

    def __call__(self, request):
        messages = json.loads(request.content)["messages"]
        self.prompts.append("\n".join(message["content"] for message in messages))
        return httpx.Response(200, json={"message": {"content": "답변 [1]"}, "prompt_eval_count": 100})


@pytest.fixture
def ollama(monkeypatch):
    fake = FakeOllama()
    real_client = httpx.Client
    monkeypatch.setattr(
        answer_module.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake), **kwargs)
    )
    return fake


def stored(chunk_id, text):
    law, article = chunk_id.rsplit(" ", 1)
    return Chunk(chunk_id, law, article, "", text, "20261008", "2026-11-02")


@pytest.fixture
def index_store(monkeypatch):
    chunks = {
        "근로기준법 제26조": stored("근로기준법 제26조", "근로기준법 제26조(해고의 예고) 사용자는 근로자를 해고"),
        "근로기준법 제11조": stored("근로기준법 제11조", "근로기준법 제11조(적용 범위) 이 법은"),
    }
    monkeypatch.setattr(cli, "get_chunks", lambda ids: [chunks[i] for i in ids if i in chunks])


def test_chunks_option_answers_from_stored_chunks_in_given_order(ollama, index_store, capsys):
    assert cli.main(["해고 예고는?", "--chunks", "근로기준법 제26조, 근로기준법 제11조"]) == 0

    prompt = ollama.prompts[0]
    assert prompt.index("[1] 근로기준법 제26조(해고의 예고)") < prompt.index("[2] 근로기준법 제11조(적용 범위)")
    out = capsys.readouterr().out
    assert "근로기준법 제26조 (2026-10-08 시행 기준)" in out
    assert out.rstrip().endswith(config.DISCLAIMER)


def test_unknown_chunk_id_fails(ollama, index_store, capsys):
    assert cli.main(["질문", "--chunks", "근로기준법 제26조,근로기준법 제999조"]) == 1

    assert "근로기준법 제999조" in capsys.readouterr().err
    assert ollama.prompts == []


def test_ask_uses_search_results_with_top_k(ollama, monkeypatch, capsys):
    calls = []
    chunk = Chunk("근로기준법 제26조", "근로기준법", "제26조", "해고의 예고", "근로기준법 제26조 본문", "20261008", "2026-11-02")
    monkeypatch.setattr(cli, "search", lambda question, k: calls.append((question, k)) or [chunk])

    assert cli.main(["질문"]) == 0

    assert calls == [("질문", config.TOP_K)]
    assert "[1] 근로기준법 제26조 (2026-10-08 시행 기준)" in capsys.readouterr().out
