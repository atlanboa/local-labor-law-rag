import json

import pytest

from lawbot import config, evaluate
from lawbot.evaluate import Judgement, KeyPointVerdict, Verdict
from lawbot.models import Answer, Chunk

QUESTIONS = [
    {"id": "q1", "question": "해고 예고는?", "type": "단일", "required": ["근로기준법 제26조"], "key_points": ["30일 전"]},
    {"id": "q2", "question": "연차와 휴일?", "type": "복합", "required": ["근로기준법 제55조", "근로기준법 제60조"], "key_points": ["a", "b"]},
    {"id": "q3", "question": "건강검진비?", "type": "근거없음", "required": [], "key_points": ["조문 없음"]},
    {"id": "q4", "question": "연차 보상?", "type": "해석필요", "required": ["근로기준법 제61조"], "key_points": ["c"]},
]


def chunk(id_):
    return Chunk(id=id_, law="근로기준법", article=id_, title="", text=f"{id_} 본문", effective_date="", collected_at="")


# q1 and q4 retrieve their required articles; q2 misses 제60조.
SEARCH_HITS = {
    "해고 예고는?": ["근로기준법 제26조", "근로기준법 제27조"],
    "연차와 휴일?": ["근로기준법 제55조"],
    "건강검진비?": ["근로기준법 제1조"],
    "연차 보상?": ["근로기준법 제61조"],
}


def fake_search(question, k):
    return [chunk(i) for i in SEARCH_HITS[question][:k]]


def fake_get_chunks(ids):
    return [chunk(i) for i in ids]


def fake_answer(question, chunks):
    return Answer(text=f"답변: {question}", cited_ids=tuple(c.id for c in chunks))


def verdict(n_points, *, met=True, fabricated=False, citations=True, behavior=True):
    return Verdict(
        key_points=[KeyPointVerdict(index=i, met=met, reason="") for i in range(1, n_points + 1)],
        fabricated=fabricated,
        fabricated_reason="",
        citations_supported=citations,
        citations_reason="",
        expected_behavior_met=behavior,
        expected_behavior_reason="",
    )


class FakeJudge:
    """Passes every answer except the one for q4, which fails its expected behavior."""

    def __init__(self):
        self.calls = []

    def __call__(self, question, chunks, reply):
        self.calls.append((question.id, [c.id for c in chunks]))
        return Judgement(verdict(len(question.key_points), behavior=question.id != "q4"), {"input_tokens": 10, "output_tokens": 2})


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    questions = tmp_path / "questions.jsonl"
    questions.write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in QUESTIONS), encoding="utf-8")
    monkeypatch.setattr(config, "QUESTIONS_PATH", questions)
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(config, "BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(evaluate, "search", fake_search)
    monkeypatch.setattr(evaluate, "get_chunks", fake_get_chunks)
    monkeypatch.setattr(evaluate, "answer", fake_answer)
    return tmp_path


def latest_run(tmp_path):
    runs = sorted((tmp_path / "results").glob("run-*.json"))
    return json.loads(runs[-1].read_text(encoding="utf-8"))


def test_search_only_skips_answer_and_judge(workspace, monkeypatch):
    def boom(*args):
        raise AssertionError("answer must not run with --only search")

    monkeypatch.setattr(evaluate, "answer", boom)
    monkeypatch.setattr(evaluate, "make_client", boom)

    assert evaluate.main(["--only", "search"]) == 0

    result = latest_run(workspace)
    scores = {item["id"]: item["search_score"] for item in result["items"]}
    assert scores == {"q1": 1, "q2": 0, "q3": None, "q4": 1}
    assert result["summary"]["search"]["overall"] == {"correct": 2, "n": 3, "score": 2 / 3}
    assert "근거없음" not in result["summary"]["search"]["by_type"]
    assert result["summary"]["answer"] is None
    assert "answer" not in result["items"][0]


def test_full_run_scores_answers_and_records_model_and_time(workspace):
    judge = FakeJudge()
    evaluate.main([], judge=judge)

    result = latest_run(workspace)
    assert {item["id"]: item["answer_score"] for item in result["items"]} == {"q1": 1, "q2": 1, "q3": 1, "q4": 0}
    assert result["summary"]["answer"]["by_type"]["해석필요"]["score"] == 0
    assert result["chat_model"] == config.CHAT_MODEL
    assert result["judge_model"] == config.JUDGE_MODEL
    assert all(item["answer"]["seconds"] >= 0 for item in result["items"])
    # Default contexts are the search results.
    assert result["items"][1]["context_ids"] == ["근로기준법 제55조"]
    assert result["summary"]["judge_usage"]["input_tokens"] == 40


def test_gold_contexts_use_required_chunks(workspace):
    judge = FakeJudge()
    evaluate.main(["--contexts", "gold"], judge=judge)

    assert dict(judge.calls) == {
        "q1": ["근로기준법 제26조"],
        "q2": ["근로기준법 제55조", "근로기준법 제60조"],
        "q3": [],
        "q4": ["근로기준법 제61조"],
    }


def test_same_answer_is_judged_once(workspace):
    judge = FakeJudge()
    evaluate.main(["--limit", "2"], judge=judge)
    evaluate.main(["--limit", "2"], judge=judge)

    assert len(judge.calls) == 2
    result = latest_run(workspace)
    assert all(item["judge"]["cached"] for item in result["items"])
    assert result["summary"]["judge_usage"]["calls"] == 0


def test_changed_answer_is_judged_again(workspace, monkeypatch):
    judge = FakeJudge()
    evaluate.main(["--limit", "1"], judge=judge)
    monkeypatch.setattr(evaluate, "answer", lambda q, chunks: Answer(text="다른 답변"))
    evaluate.main(["--limit", "1"], judge=judge)

    assert len(judge.calls) == 2


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, 1),
        ({"met": False}, 0),
        ({"fabricated": True}, 0),
        ({"citations": False}, 0),
    ],
)
def test_answer_score_needs_every_check(kwargs, expected):
    question = evaluate.Question("q", "질문", "단일", ("법 제1조",), ("a", "b"))
    assert evaluate.answer_score(question, verdict(2, **kwargs)) == expected


def test_answer_score_fails_when_judge_skips_a_key_point():
    question = evaluate.Question("q", "질문", "단일", ("법 제1조",), ("a", "b"))
    assert evaluate.answer_score(question, verdict(1)) == 0


def test_expected_behavior_counts_only_for_special_types():
    single = evaluate.Question("q", "질문", "단일", ("법 제1조",), ("a",))
    no_basis = evaluate.Question("q", "질문", "근거없음", (), ("a",))
    assert evaluate.answer_score(single, verdict(1, behavior=False)) == 1
    assert evaluate.answer_score(no_basis, verdict(1, behavior=False)) == 0


def test_baseline_save_and_compare(workspace, monkeypatch, capsys):
    evaluate.main(["--only", "search", "--save-baseline"])
    assert config.BASELINE_PATH.exists()
    capsys.readouterr()

    # q2 now finds 제60조; q1 loses 제26조.
    monkeypatch.setitem(SEARCH_HITS, "연차와 휴일?", ["근로기준법 제55조", "근로기준법 제60조"])
    monkeypatch.setitem(SEARCH_HITS, "해고 예고는?", ["근로기준법 제27조"])
    evaluate.main(["--only", "search"])

    out = capsys.readouterr().out
    assert "search on 3 shared: 0.667 -> 0.667 (+0.000)" in out
    assert "newly correct: q2" in out
    assert "newly wrong: q1" in out


def test_judge_prompt_marks_missing_chunks():
    question = evaluate.Question("q", "질문", "근거없음", (), ("조문 없음",))
    prompt = evaluate.judge_prompt(question, [], Answer(text="관련 조문이 없습니다."))
    assert "(제공된 조문 없음)" in prompt
    assert evaluate.EXPECTED_BEHAVIOR["근거없음"] in prompt


def test_judge_prompt_gives_dates_the_answer_footer_cites():
    question = evaluate.Question("q", "질문", "단일", ("근로기준법 제13조",), ("a",))
    dated = Chunk("근로기준법 제13조", "근로기준법", "제13조", "", "본문", "20261008", "2026-11-02", (), ("20261208",))
    prompt = evaluate.judge_prompt(question, [dated], Answer(text="답 [1]\n\n출처:\n[1] 근로기준법 제13조 (2026-10-08 시행 기준)"))
    assert 'effective_date="20261008"' in prompt
    assert 'pending_effective_dates="20261208"' in prompt


def test_limited_run_compares_only_shared_questions(workspace, capsys):
    evaluate.main(["--only", "search", "--save-baseline"])
    capsys.readouterr()
    evaluate.main(["--only", "search", "--limit", "1"])

    assert "search on 1 shared: 1.000 -> 1.000 (+0.000)" in capsys.readouterr().out
    assert len(list((workspace / "results").glob("run-*.json"))) == 2
