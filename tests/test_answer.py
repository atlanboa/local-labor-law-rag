import json

import httpx
import pytest

from lawbot import answer as answer_module
from lawbot import config
from lawbot.answer import answer
from lawbot.models import Chunk


def make_chunk(article, pending=()):
    return Chunk(
        id=f"근로기준법 {article}",
        law="근로기준법",
        article=article,
        title="",
        text=f"근로기준법 {article}(제목) {article} 본문",
        effective_date="20261008",
        collected_at="2026-11-02",
        pending_effective_dates=pending,
    )


CHUNKS = [make_chunk("제26조"), make_chunk("제13조", pending=("20261208",)), make_chunk("제36조")]


class FakeOllama:
    def __init__(self, content="답변", prompt_eval_count=500, failures=0):
        self.content = content
        self.prompt_eval_count = prompt_eval_count
        self.failures = failures
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if len(self.requests) <= self.failures:
            return httpx.Response(500, json={"error": "CUDA error: shared object initialization failed"})
        body = {"message": {"role": "assistant", "content": self.content}, "prompt_eval_count": self.prompt_eval_count}
        return httpx.Response(200, json=body)

    def payload(self, index=-1):
        return json.loads(self.requests[index].content)


@pytest.fixture
def ollama(monkeypatch):
    fake = FakeOllama()
    real_client = httpx.Client
    monkeypatch.setattr(
        answer_module.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake), **kwargs)
    )
    return fake


def test_calls_chat_model_deterministically_with_numbered_chunks(ollama):
    answer("해고 예고는?", CHUNKS)

    request = ollama.requests[0]
    assert request.url.path == "/api/chat"
    payload = ollama.payload()
    assert payload["model"] == config.CHAT_MODEL
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0, "num_ctx": config.NUM_CTX}
    prompt = "\n".join(message["content"] for message in payload["messages"])
    assert "[1] 근로기준법 제26조(제목) 제26조 본문" in prompt
    assert "[3] 근로기준법 제36조(제목) 제36조 본문" in prompt
    assert "해고 예고는?" in prompt


def test_cited_numbers_become_chunk_ids_and_out_of_range_numbers_are_dropped(ollama):
    ollama.content = "예고해야 합니다 [1]. 감독관 [2, 7]. 다시 [1][9][0]."

    result = answer("질문", CHUNKS)

    assert result.cited_ids == ("근로기준법 제26조", "근로기준법 제13조")


def test_text_appends_sources_pending_amendments_and_disclaimer(ollama):
    ollama.content = "30일 전에 예고해야 합니다 [1]. 감독관 [2]."

    result = answer("질문", CHUNKS)

    assert result.text.startswith("30일 전에 예고해야 합니다 [1]. 감독관 [2].")
    assert "[1] 근로기준법 제26조 (2026-10-08 시행 기준)" in result.text
    assert "[2] 근로기준법 제13조 (2026-10-08 시행 기준)" in result.text
    assert "근로기준법 제13조: 2026-12-08 시행 예정 개정이 있습니다." in result.text
    assert "제36조" not in result.text
    assert result.text.endswith(config.DISCLAIMER)


def test_pending_amendment_of_uncited_chunk_is_not_announced(ollama):
    ollama.content = "예고 [1]"

    result = answer("질문", CHUNKS)

    assert "시행 예정" not in result.text


def test_answer_without_citations_still_lists_searched_chunks_and_disclaimer(ollama):
    ollama.content = "관련 조문이 없습니다."

    result = answer("질문", CHUNKS)

    assert result.cited_ids == ()
    assert all(chunk.id in result.text for chunk in CHUNKS)
    assert result.text.endswith(config.DISCLAIMER)


def test_empty_chunks_answer_without_calling_llm(ollama):
    result = answer("질문", [])

    assert ollama.requests == []
    assert "관련 조문을 찾지 못했습니다" in result.text
    assert result.cited_ids == ()
    assert result.text.endswith(config.DISCLAIMER)


@pytest.mark.parametrize(("count", "warned"), [(config.NUM_CTX - 10, True), (config.NUM_CTX // 2, False)])
def test_warns_on_stderr_when_prompt_nears_num_ctx(ollama, capsys, count, warned):
    ollama.prompt_eval_count = count

    answer("질문", CHUNKS)

    assert ("num_ctx" in capsys.readouterr().err) is warned


def test_retries_once_after_ollama_failure(ollama):
    ollama.failures = 1
    ollama.content = "예고 [1]"

    result = answer("질문", CHUNKS)

    assert len(ollama.requests) == 2
    assert result.cited_ids == ("근로기준법 제26조",)


def test_second_failure_raises(ollama):
    ollama.failures = 2

    with pytest.raises(httpx.HTTPStatusError):
        answer("질문", CHUNKS)

    assert len(ollama.requests) == 2
