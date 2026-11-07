"""Score retrieval and answers against eval/questions.jsonl.

Usage: uv run eval [--only search] [--contexts gold] [--limit N] [--repeat N] [--save-baseline]
"""

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import dotenv_values
from pydantic import BaseModel

from lawbot import config
from lawbot.answer import answer
from lawbot.models import Answer, Chunk
from lawbot.search import get_chunks, search

# Bump when the judge prompt or schema changes, so cached verdicts are not reused.
RUBRIC_VERSION = "2"
NO_BASIS = "근거없음"
NEEDS_INTERPRETATION = "해석필요"

EXPECTED_BEHAVIOR = {
    "단일": "제공된 그 조문으로 답한다.",
    "복합": "제공된 여러 조문을 합쳐 답한다.",
    NO_BASIS: "관련 조문이 없다고 말하고, 조문이나 수치를 지어내지 않는다.",
    NEEDS_INTERPRETATION: (
        "조문이 말하는 데까지만 답하고, 나머지는 판례나 해석 또는 수집하지 않은 법령이 필요하다고 밝힌다. "
        "단정하지 않고 노무사나 고용노동부(1350)를 안내한다."
    ),
}

JUDGE_SYSTEM = """당신은 한국 노동법 상담봇의 답변을 채점한다. 근거는 사용자 메시지에 제공된 조문뿐이다. 당신이 아는 법률 지식으로 조문을 보충하지 않는다.

채점 항목:
1. key_points: 각 핵심 내용이 답변에 들어 있는지 판단한다. 원문의 조건(예외, 기한, 금액 기준)을 빠뜨렸으면 충족하지 않은 것이다. 같은 뜻이면 표현이 달라도 충족이다.
2. fabricated: 답변이 제공된 조문에 없는 법적 내용(조문 번호, 기한, 금액, 비율, 요건, 효과)을 사실처럼 말했으면 true다. 일반적인 안내(노무사나 고용노동부 문의 권유, 면책 문구)는 지어낸 것이 아니다. 조문이 하나도 제공되지 않았는데 구체적인 법적 내용을 단정하면 true다.
3. citations_supported: 답변이 인용한 조문이 모두 제공된 조문에 있고, 답변에서 그 조문을 근거로 한 내용을 실제로 뒷받침하면 true다. 인용이 없는데 법적 내용을 말했으면 false다. 관련 조문이 없다고 답하는 문항에서 인용이 없으면 true다.
4. expected_behavior_met: 질문 유형별 정답 행동을 지켰는지 판단한다.

답변 끝의 출처 목록, 시행 기준일, 시행 예정 안내, 면책 문구는 프로그램이 청크의 effective_date와 pending_effective_dates로 붙인 것이다. 지어낸 내용으로 보지 않고, 그 앞의 본문만 채점한다.

reason에는 답변과 조문의 어느 부분을 보고 판단했는지 한두 문장으로 쓴다."""


class KeyPointVerdict(BaseModel):
    index: int
    met: bool
    reason: str


class Verdict(BaseModel):
    key_points: list[KeyPointVerdict]
    fabricated: bool
    fabricated_reason: str
    citations_supported: bool
    citations_reason: str
    expected_behavior_met: bool
    expected_behavior_reason: str


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    question: str
    type: str
    required: tuple[str, ...]
    key_points: tuple[str, ...]


@dataclass(slots=True)
class Judgement:
    verdict: Verdict
    usage: dict = field(default_factory=dict)


Judge = Callable[[Question, list[Chunk], Answer], Judgement]


def load_questions(path: Path) -> list[Question]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [
        Question(
            id=row["id"],
            question=row["question"],
            type=row["type"],
            required=tuple(row["required"]),
            key_points=tuple(row["key_points"]),
        )
        for row in rows
    ]


def search_score(question: Question, retrieved_ids: Iterable[str]) -> int | None:
    if question.type == NO_BASIS:
        return None
    return int(set(question.required) <= set(retrieved_ids))


def answer_score(question: Question, verdict: Verdict) -> int:
    met = {kp.index for kp in verdict.key_points if kp.met}
    all_met = met >= set(range(1, len(question.key_points) + 1))
    behavior_ok = verdict.expected_behavior_met or question.type not in (NO_BASIS, NEEDS_INTERPRETATION)
    return int(all_met and not verdict.fabricated and verdict.citations_supported and behavior_ok)


def judge_prompt(question: Question, chunks: list[Chunk], reply: Answer) -> str:
    key_points = "\n".join(f"{i}. {kp}" for i, kp in enumerate(question.key_points, start=1))
    if chunks:
        provided = "\n\n".join(
            f'<chunk id="{c.id}" effective_date="{c.effective_date}" '
            f'pending_effective_dates="{",".join(c.pending_effective_dates)}">\n{c.text}\n</chunk>'
            for c in chunks
        )
    else:
        provided = "(제공된 조문 없음)"
    cited = ", ".join(reply.cited_ids) or "(없음)"
    return f"""<question>{question.question}</question>
<type>{question.type}</type>
<expected_behavior>{EXPECTED_BEHAVIOR[question.type]}</expected_behavior>
<key_points>
{key_points}
</key_points>
<provided_chunks>
{provided}
</provided_chunks>
<answer>
{reply.text}
</answer>
<cited_ids>{cited}</cited_ids>

key_points의 index는 위 번호(1부터)를 그대로 쓰고, 모든 번호에 대해 판단한다."""


def claude_judge(client: anthropic.Anthropic) -> Judge:
    def judge(question: Question, chunks: list[Chunk], reply: Answer) -> Judgement:
        response = client.messages.parse(
            model=config.JUDGE_MODEL,
            max_tokens=16000,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": judge_prompt(question, chunks, reply)}],
            output_format=Verdict,
        )
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            raise JudgeError(f"stop_reason={response.stop_reason} request_id={response._request_id}")
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return Judgement(response.parsed_output, usage)

    return judge


class JudgeError(Exception):
    pass


def cache_key(question: Question, chunks: list[Chunk], reply: Answer) -> str:
    material = {
        "judge_model": config.JUDGE_MODEL,
        "rubric_version": RUBRIC_VERSION,
        "question": [question.question, question.type, list(question.key_points)],
        "answer": [reply.text, list(reply.cited_ids)],
        "chunk_ids": [c.id for c in chunks],
    }
    blob = json.dumps(material, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def cached_judge(judge: Judge, cache_dir: Path, question: Question, chunks: list[Chunk], reply: Answer) -> tuple[Judgement, bool]:
    path = cache_dir / f"{cache_key(question, chunks, reply)}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return Judgement(Verdict.model_validate(data["verdict"]), data["usage"]), True
    judgement = judge(question, chunks, reply)
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {"verdict": judgement.verdict.model_dump(), "usage": judgement.usage}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return judgement, False


def summarize(items: list[dict], key: str) -> dict | None:
    scored = [item for item in items if item.get(key) is not None]
    if not scored:
        return None
    by_type: dict[str, list[int]] = {}
    for item in scored:
        by_type.setdefault(item["type"], []).append(item[key])

    def stat(scores: list[int]) -> dict:
        return {"correct": sum(scores), "n": len(scores), "score": sum(scores) / len(scores)}

    return {
        "overall": stat([item[key] for item in scored]),
        "by_type": {t: stat(s) for t, s in by_type.items()},
    }


def run(
    questions: list[Question],
    *,
    only_search: bool,
    gold_contexts: bool,
    search_fn: Callable[[str, int], list[Chunk]],
    get_chunks_fn: Callable[[Iterable[str]], list[Chunk]],
    answer_fn: Callable[[str, list[Chunk]], Answer],
    judge: Judge | None,
    cache_dir: Path,
    repeat: int = 1,
    log: Callable[[str], None] = print,
) -> dict:
    items = []
    contexts = []
    for question in questions:
        retrieved = search_fn(question.question, config.TOP_K)
        items.append({
            "id": question.id,
            "type": question.type,
            "question": question.question,
            "required": list(question.required),
            "retrieved_ids": [c.id for c in retrieved],
            "search_score": search_score(question, (c.id for c in retrieved)),
        })
        contexts.append(get_chunks_fn(question.required) if gold_contexts else retrieved)
    if only_search:
        for n, item in enumerate(items, start=1):
            log(f"[{n}/{len(items)}] {item['id']} search={item['search_score']}")

    # Sequential on purpose: answer() runs on a single local GPU through Ollama.
    # Repeat whole passes, not one question back to back: Gemma's output at temperature 0 still
    # varies with Ollama's state, and asking the same question twice in a row hides that.
    for r in range(0 if only_search else repeat):
        for n, (question, item, chunks) in enumerate(zip(questions, items, contexts), start=1):
            started = time.perf_counter()
            reply = answer_fn(question.question, chunks)
            seconds = time.perf_counter() - started
            judgement, cached = cached_judge(judge, cache_dir, question, chunks, reply)
            item["context_ids"] = [c.id for c in chunks]
            item.setdefault("runs", []).append({
                "answer": {"text": reply.text, "cited_ids": list(reply.cited_ids), "seconds": round(seconds, 3)},
                "judge": judgement.verdict.model_dump() | {"cached": cached, "usage": judgement.usage},
                "answer_score": answer_score(question, judgement.verdict),
            })
            log(f"[{r + 1}/{repeat}][{n}/{len(items)}] {question.id} search={item['search_score']} answer={item['runs'][-1]['answer_score']}")

    for item in items:
        if "runs" in item:
            scores = [run["answer_score"] for run in item["runs"]]
            # Strict majority: with repeat 3 a question counts as correct when 2 or 3 runs pass.
            item["answer_score"] = int(2 * sum(scores) > len(scores))

    result = {
        "options": {
            "only": "search" if only_search else None,
            "contexts": "gold" if gold_contexts else "search",
            "repeat": None if only_search else repeat,
        },
        "chat_model": None if only_search else config.CHAT_MODEL,
        "judge_model": None if only_search else config.JUDGE_MODEL,
        "rubric_version": RUBRIC_VERSION,
        "top_k": config.TOP_K,
        "max_chunks": config.MAX_CHUNKS,
        "summary": {"search": summarize(items, "search_score"), "answer": summarize(items, "answer_score")},
        "items": items,
    }
    if not only_search:
        runs = [run for item in items for run in item["runs"]]
        judged = [run for run in runs if not run["judge"]["cached"]]
        # Correct answers in each pass, before the majority vote.
        result["summary"]["answer_runs"] = [sum(item["runs"][r]["answer_score"] for item in items) for r in range(repeat)]
        result["summary"]["answer_seconds"] = round(sum(run["answer"]["seconds"] for run in runs), 3)
        result["summary"]["judge_usage"] = {
            "calls": len(judged),
            "cached": len(runs) - len(judged),
            "input_tokens": sum(item["judge"]["usage"].get("input_tokens", 0) for item in judged),
            "output_tokens": sum(item["judge"]["usage"].get("output_tokens", 0) for item in judged),
        }
    return result


def format_summary(result: dict) -> list[str]:
    lines = []
    for kind in ("search", "answer"):
        summary = result["summary"][kind]
        if summary is None:
            continue
        o = summary["overall"]
        lines.append(f"{kind}: {o['score']:.3f} ({o['correct']}/{o['n']})")
        for t, s in summary["by_type"].items():
            lines.append(f"  {t}: {s['score']:.3f} ({s['correct']}/{s['n']})")
    if len(result["summary"].get("answer_runs", [])) > 1:
        n = result["summary"]["answer"]["overall"]["n"]
        per_run = ", ".join(f"{c}/{n}" for c in result["summary"]["answer_runs"])
        lines.append(f"  answer per run: {per_run}; overall is the majority of {len(result['summary']['answer_runs'])} runs")
    if "judge_usage" in result["summary"]:
        u = result["summary"]["judge_usage"]
        lines.append(f"chat model: {result['chat_model']}, answer time: {result['summary']['answer_seconds']:.1f}s")
        lines.append(
            f"judge: {result['judge_model']} calls={u['calls']} cached={u['cached']} "
            f"input_tokens={u['input_tokens']} output_tokens={u['output_tokens']}"
        )
    return lines


def compare(result: dict, baseline: dict) -> list[str]:
    lines = ["vs baseline:"]
    for kind, key in (("search", "search_score"), ("answer", "answer_score")):
        if result["summary"][kind] is None or baseline["summary"].get(kind) is None:
            continue
        if kind == "answer" and result["options"]["contexts"] != baseline["options"]["contexts"]:
            lines.append(f"  answer: skipped, contexts differ ({result['options']['contexts']} vs {baseline['options']['contexts']})")
            continue
        # Compare on questions scored in both runs, so --limit runs line up with a full baseline.
        old = {item["id"]: item.get(key) for item in baseline["items"]}
        shared = [item for item in result["items"] if item.get(key) is not None and old.get(item["id"]) is not None]
        if not shared:
            continue
        before_score = sum(old[item["id"]] for item in shared) / len(shared)
        now_score = sum(item[key] for item in shared) / len(shared)
        lines.append(f"  {kind} on {len(shared)} shared: {before_score:.3f} -> {now_score:.3f} ({now_score - before_score:+.3f})")
        fixed = [item["id"] for item in shared if item[key] > old[item["id"]]]
        broke = [item["id"] for item in shared if item[key] < old[item["id"]]]
        lines.append(f"    newly correct: {', '.join(fixed) or '-'}")
        lines.append(f"    newly wrong: {', '.join(broke) or '-'}")
    return lines


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="eval", description="Score retrieval and answers on eval/questions.jsonl.")
    parser.add_argument("--only", choices=["search"], help="score retrieval only; no LLM calls")
    parser.add_argument("--contexts", choices=["search", "gold"], default="search", help="chunks given to answer()")
    parser.add_argument("--limit", type=int, help="use the first N questions")
    parser.add_argument("--repeat", type=int, default=1, help="answer every question N times; a question counts when most runs pass")
    parser.add_argument("--save-baseline", action="store_true", help="write this run to eval/baseline.json")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be 1 or more")
    return args


def make_client() -> anthropic.Anthropic:
    # Falls back to the environment when .env has no key.
    key = dotenv_values(config.ROOT / ".env").get("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=key or None)


def main(argv: list[str] | None = None, judge: Judge | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    only_search = args.only == "search"
    questions = load_questions(config.QUESTIONS_PATH)[: args.limit]
    if not only_search and judge is None:
        judge = claude_judge(make_client())

    started_at = datetime.now()
    result = {"started_at": started_at.isoformat(timespec="seconds")} | run(
        questions,
        only_search=only_search,
        gold_contexts=args.contexts == "gold",
        search_fn=search,
        get_chunks_fn=get_chunks,
        answer_fn=answer,
        judge=judge,
        cache_dir=config.RESULTS_DIR / "judge-cache",
        repeat=args.repeat,
    )
    result["options"]["limit"] = args.limit

    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS_DIR / f"run-{started_at:%Y%m%d-%H%M%S-%f}.json"
    text = json.dumps(result, ensure_ascii=False, indent=2)
    out.write_text(text, encoding="utf-8")

    lines = format_summary(result)
    if config.BASELINE_PATH.exists():
        lines += compare(result, json.loads(config.BASELINE_PATH.read_text(encoding="utf-8")))
    if args.save_baseline:
        config.BASELINE_PATH.write_text(text, encoding="utf-8")
        lines.append(f"baseline saved: {config.BASELINE_PATH}")
    lines.append(f"results: {out}")
    print("\n".join(lines))
    return 0
