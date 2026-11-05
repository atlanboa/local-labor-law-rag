"""Check this checkout against eval/baseline.json: Ollama, pytest, index, search eval, answer eval.

Usage: uv run python scripts/verify.py [--baseline PATH]

Uses only the folder it runs in: data/chroma, eval/results, .env of this checkout.
Never passes --save-baseline. Never prints the API key; only says whether .env has one.
Exit code: 0 PASS, 1 FAIL, 2 stopped before a verdict.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values

from lawbot import config, index

CHILD_ENV = os.environ | {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


class Stop(Exception):
    pass


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=config.ROOT, env=CHILD_ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")


def tail(text: str, n: int = 15) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


def check_checkout() -> str:
    top = run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    if not top or Path(top).resolve() != config.ROOT.resolve():
        raise Stop(f"lawbot 패키지가 다른 폴더를 가리킨다: config.ROOT={config.ROOT}, git 최상위={top}. 이 폴더에서 uv sync 후 다시 실행한다")
    return f"폴더 {config.ROOT}"


def check_ollama() -> str:
    url = f"{config.OLLAMA_URL}/api/tags"
    try:
        response = httpx.get(url, timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise Stop(f"Ollama가 {config.OLLAMA_URL}에서 응답하지 않는다: {type(error).__name__}: {error}")
    installed = {m["name"] for m in response.json().get("models", [])}
    missing = [name for name in (config.EMBED_MODEL, config.CHAT_MODEL) if name not in installed]
    if missing:
        raise Stop(f"Ollama에 없는 모델: {', '.join(missing)} (설치됨: {', '.join(sorted(installed))})")
    return f"Ollama {config.OLLAMA_URL}, 임베딩 {config.EMBED_MODEL}, 채팅 {config.CHAT_MODEL}"


def check_pytest() -> str:
    proc = run(["uv", "run", "pytest", "-q"])
    if proc.returncode != 0:
        raise Stop(f"pytest 실패(exit {proc.returncode}):\n{tail(proc.stdout + proc.stderr)}")
    return tail(proc.stdout, 1)


def check_index() -> str:
    proc = run(["uv", "run", "index"])
    if proc.returncode != 0:
        raise Stop(f"index 실패(exit {proc.returncode}):\n{tail(proc.stdout + proc.stderr)}")
    saved = re.search(r"(\d+)개 청크를", proc.stdout)
    if not saved:
        raise Stop(f"index 출력에서 저장 개수를 찾지 못했다:\n{tail(proc.stdout)}")
    lines = sum(1 for line in index.CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    stored = index.open_collection().count()
    counts = f"저장 {saved.group(1)}, chunks.jsonl {lines}줄, Chroma {stored}개"
    if not int(saved.group(1)) == lines == stored:
        raise Stop(f"개수 불일치: {counts}")
    return counts


def run_eval(args: list[str]) -> dict:
    proc = run(["uv", "run", "eval", *args])
    found = re.search(r"^results: (.+)$", proc.stdout, re.M)
    if proc.returncode != 0 or not found:
        raise Stop(f"eval {' '.join(args)} 실패(exit {proc.returncode}). Ollama 콜드 로드 오류면 한 번 다시 실행한다:\n{tail(proc.stdout + proc.stderr)}")
    path = Path(found.group(1).strip())
    return json.loads(path.read_text(encoding="utf-8")) | {"_path": str(path)}


def has_api_key() -> bool:
    env_file = config.ROOT / ".env"
    return env_file.exists() and bool(dotenv_values(env_file).get("ANTHROPIC_API_KEY"))


def compare(kind: str, result: dict, baseline: dict) -> tuple[bool, list[str]]:
    key = f"{kind}_score"
    now, base = result["summary"][kind], baseline["summary"][kind]
    o, b = now["overall"], base["overall"]
    ok = o["score"] >= b["score"]
    lines = [f"{kind}: {b['score']:.3f} ({b['correct']}/{b['n']}) -> {o['score']:.3f} ({o['correct']}/{o['n']}) {'OK' if ok else '낮음'}"]
    for t in sorted(set(now["by_type"]) | set(base["by_type"])):
        n, p = now["by_type"].get(t), base["by_type"].get(t)
        fmt = lambda s: f"{s['score']:.3f} ({s['correct']}/{s['n']})" if s else "-"
        delta = f"{n['score'] - p['score']:+.3f}" if n and p else "?"
        lines.append(f"  {t}: {fmt(p)} -> {fmt(n)} {delta}")
    old = {item["id"]: item.get(key) for item in baseline["items"]}
    broke = [i["id"] for i in result["items"] if old.get(i["id"]) == 1 and i.get(key) == 0]
    fixed = [i["id"] for i in result["items"] if old.get(i["id"]) == 0 and i.get(key) == 1]
    lines.append(f"  새로 틀림: {', '.join(broke) or '-'}")
    lines.append(f"  새로 맞음: {', '.join(fixed) or '-'}")
    return ok, lines


def setting_notes(result: dict, baseline: dict) -> list[str]:
    notes = []
    for field in ("chat_model", "rubric_version", "top_k"):
        if result.get(field) is not None and result.get(field) != baseline.get(field):
            notes.append(f"주의: {field}가 기준선과 다르다 ({baseline.get(field)} -> {result.get(field)})")
    if baseline["options"].get("limit") or baseline["options"].get("only"):
        notes.append("주의: 기준선이 전체 실행이 아니다")
    return notes


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=config.BASELINE_PATH, help="compare against this file (default eval/baseline.json)")
    args = parser.parse_args()

    started = time.perf_counter()
    report: list[str] = [f"verify {datetime.now():%Y-%m-%d %H:%M:%S}"]
    verdict = "STOP"
    files: list[str] = []

    def step(name: str, fn, describe=str):
        t = time.perf_counter()
        try:
            value = fn()
        except Stop as error:
            report.append(f"[FAIL] {name} ({time.perf_counter() - t:.0f}초)\n{error}")
            raise
        report.append(f"[ OK ] {name} ({time.perf_counter() - t:.0f}초): {describe(value)}")
        return value

    try:
        step("0 폴더", check_checkout)
        step("1 준비", check_ollama)
        step("2 pytest", check_pytest)
        step("3 index", check_index)
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        report.append(f"기준선: {args.baseline}")

        search = step("4 eval --only search", lambda: run_eval(["--only", "search"]), lambda r: r["_path"])
        files.append(search["_path"])
        passed, lines = compare("search", search, baseline)
        report += lines + setting_notes(search, baseline)

        if has_api_key():
            full = step("5 eval", lambda: run_eval([]), lambda r: r["_path"])
            files.append(full["_path"])
            answer_ok, lines = compare("answer", full, baseline)
            passed = passed and answer_ok
            u = full["summary"]["judge_usage"]
            report += lines + setting_notes(full, baseline)
            report.append(f"  Claude API 호출 {u['calls']}회, 캐시 {u['cached']}회, 입력 {u['input_tokens']} 출력 {u['output_tokens']} 토큰, 답변 {full['summary']['answer_seconds']:.0f}초")
            verdict = "PASS" if passed else "FAIL"
        else:
            report.append("[SKIP] 5 eval: .env에 ANTHROPIC_API_KEY가 없다. 답변 평가를 건너뛰었다. 판정은 검색 점수만 본다")
            verdict = "PASS (검색만)" if passed else "FAIL"
    except Stop:
        pass

    report.append(f"판정: {verdict}")
    report.append(f"걸린 시간: {time.perf_counter() - started:.0f}초")
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS_DIR / f"verify-{datetime.now():%Y%m%d-%H%M%S}.txt"
    report += [f"결과: {path}" for path in files] + [f"보고: {out}"]
    text = "\n".join(report)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return {"PASS": 0, "PASS (검색만)": 0, "FAIL": 1}.get(verdict, 2)


if __name__ == "__main__":
    sys.exit(main())
