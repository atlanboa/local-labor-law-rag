import re
import sys
import time
from dataclasses import dataclass

import httpx

from lawbot import config
from lawbot.models import Answer, Chunk

SYSTEM_PROMPT = """너는 한국 노동법 질문에 답하는 상담 도우미다. 아래 규칙을 지킨다.
1. 사용자가 준 조문만 근거로 답한다. 너가 알고 있는 다른 법 지식이나 판례는 쓰지 않는다.
2. 근거로 쓴 조문은 문장 끝에 [1], [2]처럼 조문 번호로 표시한다. 문장마다 그 내용이 실제로 적힌 조문 번호를 단다.
3. 조문에 없는 내용은 지어내지 않는다. 조문에 적힌 문장을 바꿔 말할 때도 조건과 대상을 넓히거나 좁히지 않는다.
4. 답에 쓰는 조문의 조건, 금액, 기간, 예외(다만, 각 호)는 빠뜨리지 않는다.
5. 어떤 규정이 적용되는지를 목록이나 표로 판단할 때는 조와 항 번호까지 정확히 대조한다. 목록에 없는 조항은 적용된다고 말하지 않는다.
6. 조문만으로 확정할 수 없으면 조문이 말하는 데까지만 답하고, 조문만으로는 확정할 수 없다고 밝힌다. 단정하지 않는다.
7. 질문과 관련된 조문이 없으면 관련 조문이 없다고 말한다.
8. 한국어로 간결하게 답한다. 출처 목록과 면책 문구는 따로 붙으니 쓰지 않는다."""

NO_CHUNKS_TEXT = "관련 조문을 찾지 못했습니다. 수집한 법령에서 이 질문의 근거가 될 조문을 찾지 못해 답할 수 없습니다."
CTX_WARN_RATIO = 0.9
TIMEOUT_SECONDS = 300
CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass(frozen=True, slots=True)
class ChatStats:
    seconds: float
    prompt_eval_count: int | None


def answer(question: str, chunks: list[Chunk]) -> Answer:
    return answer_with_stats(question, chunks)[0]


def answer_with_stats(question: str, chunks: list[Chunk]) -> tuple[Answer, ChatStats | None]:
    if not chunks:
        return Answer(f"{NO_CHUNKS_TEXT}\n\n출처: 없음\n\n{config.DISCLAIMER}"), None

    started = time.perf_counter()
    response = chat(build_messages(question, chunks))
    stats = ChatStats(time.perf_counter() - started, response.get("prompt_eval_count"))
    if stats.prompt_eval_count is not None and stats.prompt_eval_count >= CTX_WARN_RATIO * config.NUM_CTX:
        print(
            f"경고: prompt_eval_count {stats.prompt_eval_count}가 num_ctx {config.NUM_CTX}에 가깝다. "
            "프롬프트가 잘렸을 수 있다.",
            file=sys.stderr,
        )

    reply = response["message"]["content"].strip()
    cited = cited_numbers(reply, len(chunks))
    cited_chunks = [chunks[number - 1] for number in cited]
    text = "\n\n".join([reply, sources(chunks, cited), *pending_notes(cited_chunks), config.DISCLAIMER])
    return Answer(text, tuple(chunk.id for chunk in cited_chunks)), stats


def build_messages(question: str, chunks: list[Chunk]) -> list[dict[str, str]]:
    numbered = "\n\n".join(f"[{number}] {chunk.text}" for number, chunk in enumerate(chunks, start=1))
    user = f"조문:\n\n{numbered}\n\n질문: {question}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def chat(messages: list[dict[str, str]]) -> dict:
    payload = {
        "model": config.CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": config.NUM_CTX},
    }
    with httpx.Client(base_url=config.OLLAMA_URL, timeout=TIMEOUT_SECONDS) as client:
        try:
            return post_chat(client, payload)
        except httpx.HTTPError as error:
            # Cold model loads have failed once with a CUDA error that did not recur.
            print(f"Ollama 호출 실패({describe(error)}), 한 번 재시도한다", file=sys.stderr)
            return post_chat(client, payload)


def post_chat(client: httpx.Client, payload: dict) -> dict:
    response = client.post("/api/chat", json=payload)
    response.raise_for_status()
    return response.json()


def describe(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}: {error.response.text[:200]}"
    return type(error).__name__


def cited_numbers(reply: str, count: int) -> list[int]:
    numbers = []
    for match in CITATION.finditer(reply):
        for part in match.group(1).split(","):
            number = int(part)
            if 1 <= number <= count and number not in numbers:
                numbers.append(number)
    return numbers


def sources(chunks: list[Chunk], cited: list[int]) -> str:
    if not cited:
        lines = [f"- {chunk.id} ({iso(chunk.effective_date)} 시행 기준)" for chunk in chunks]
        return "출처: 답변이 인용한 조문이 없습니다. 검색된 조문:\n" + "\n".join(lines)
    lines = [f"[{number}] {chunks[number - 1].id} ({iso(chunks[number - 1].effective_date)} 시행 기준)" for number in cited]
    return "출처:\n" + "\n".join(lines)


def pending_notes(cited_chunks: list[Chunk]) -> list[str]:
    return [
        f"{chunk.id}: {iso(day)} 시행 예정 개정이 있습니다."
        for chunk in cited_chunks
        for day in chunk.pending_effective_dates
    ]


def iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
