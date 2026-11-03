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


def test_chunks_option_builds_chunks_from_raw_data(ollama, capsys):
    ids = "근로기준법 제26조, 근로기준법 시행령 별표 1"

    assert cli.main(["해고 예고는?", "--chunks", ids]) == 0

    prompt = ollama.prompts[0]
    assert "[1] 근로기준법 제26조(해고의 예고) 사용자는 근로자를 해고" in prompt
    assert "3개월 미만인 경우" in prompt
    assert "[2] 근로기준법 시행령 별표 1 상시 4명 이하의" in prompt
    out = capsys.readouterr().out
    assert "근로기준법 제26조 (2026-10-08 시행 기준)" in out
    assert out.rstrip().endswith(config.DISCLAIMER)


def test_raw_chunks_carry_pending_effective_dates_per_article():
    chunks = cli.load_chunks(["근로기준법 제13조", "근로기준법 제116조", "근로기준법 제26조"])

    assert [chunk.pending_effective_dates for chunk in chunks] == [("20261208",), ("20261208", "20270101"), ()]


def test_raw_chunks_skip_chapter_headings_and_cover_every_eval_answer_key():
    chunks = cli.chunks_from_raw(config.RAW_DIR)

    articles = [chunk for chunk in chunks.values() if chunk.law == "근로기준법" and "별표" not in chunk.article]
    assert len(articles) == 132
    keys = {key for line in config.QUESTIONS_PATH.open(encoding="utf-8") for key in json.loads(line)["required"]}
    assert keys <= chunks.keys()


def test_unknown_chunk_id_fails(ollama, capsys):
    assert cli.main(["질문", "--chunks", "근로기준법 제999조"]) == 1

    assert "근로기준법 제999조" in capsys.readouterr().err
    assert ollama.prompts == []


def test_ask_without_chunks_reports_unimplemented_search(ollama, capsys):
    assert cli.main(["질문"]) == 1

    assert "--chunks" in capsys.readouterr().err


def test_ask_uses_search_results_with_top_k(ollama, monkeypatch, capsys):
    calls = []
    chunk = Chunk("근로기준법 제26조", "근로기준법", "제26조", "해고의 예고", "근로기준법 제26조 본문", "20261008", "2026-11-02")
    monkeypatch.setattr(cli, "search", lambda question, k: calls.append((question, k)) or [chunk])

    assert cli.main(["질문"]) == 0

    assert calls == [("질문", config.TOP_K)]
    assert "[1] 근로기준법 제26조 (2026-10-08 시행 기준)" in capsys.readouterr().out
