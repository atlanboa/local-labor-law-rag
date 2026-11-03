import argparse
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import httpx

from lawbot import config
from lawbot.answer import answer_with_stats
from lawbot.models import Chunk
from lawbot.search import search

PENDING_GROUP = re.compile(r"(\d{8}):(.*?)(?=\d{8}:|$)")
ARTICLE_PREFIX = re.compile(r"제\d+조(?:의\d+)?")


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def flatten(value) -> Iterator[str]:
    if isinstance(value, list):
        for item in value:
            yield from flatten(item)
    elif isinstance(value, str) and value.strip():
        yield value.strip()


def number(digits: str) -> str:
    return str(int(digits))


def article_id(unit: dict) -> str:
    branch = unit.get("조문가지번호")
    suffix = f"의{number(branch)}" if branch and int(branch) else ""
    return f"제{number(unit['조문번호'])}조{suffix}"


def article_body(unit: dict) -> str:
    parts = [unit["조문내용"]]
    for clause in as_list(unit.get("항")):
        parts.extend(flatten(clause.get("항내용")))
        for item in as_list(clause.get("호")):
            parts.extend(flatten(item.get("호내용")))
            for sub in as_list(item.get("목")):
                parts.extend(flatten(sub.get("목내용")))
    return " ".join(part.strip() for part in parts)


def annex_id(unit: dict) -> str:
    branch = int(unit.get("별표가지번호") or 0)
    annex = f"별표 {number(unit['별표번호'])}" + (f"의{branch}" if branch else "")
    # 근로기준법 has a single annex numbered 0000, printed as "[별표]".
    return "별표" if annex == "별표 0" else annex


def pending_by_article(dates: str | None) -> dict[str, list[str]]:
    pending: dict[str, list[str]] = {}
    for day, items in PENDING_GROUP.findall(dates or ""):
        for item in items.split(","):
            match = ARTICLE_PREFIX.match(item.strip())
            if match and day not in pending.setdefault(match.group(), []):
                pending[match.group()].append(day)
    return pending


def chunks_from_raw(raw_dir: Path) -> dict[str, Chunk]:
    manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
    chunks = {}
    for entry in manifest["files"]:
        if entry["params"]["target"] != "eflaw":
            continue
        law_json = json.loads((raw_dir / entry["file"]).read_text(encoding="utf-8"))["법령"]
        info = law_json["기본정보"]
        law = info["법령명_한글"]
        pending = pending_by_article(manifest["article_effective_dates"].get(law))

        def make(article: str, title: str, text: str, pending_dates: tuple[str, ...] = ()) -> None:
            chunk_id = f"{law} {article}"
            chunks[chunk_id] = Chunk(
                id=chunk_id,
                law=law,
                article=article,
                title=title,
                text=text,
                effective_date=info["시행일자"],
                collected_at=manifest["collected_at"],
                pending_effective_dates=pending_dates,
            )

        for unit in as_list(law_json["조문"]["조문단위"]):
            if unit["조문여부"] != "조문":
                continue
            article = article_id(unit)
            make(article, unit.get("조문제목", ""), f"{law} {article_body(unit)}", tuple(pending.get(article, ())))
        for unit in as_list((law_json.get("별표") or {}).get("별표단위")):
            article = annex_id(unit)
            body = "\n".join(line.rstrip() for line in flatten(unit["별표내용"]))
            make(article, unit["별표제목"], f"{law} {article} {unit['별표제목']}\n{body}")
    return chunks


def load_chunks(ids: list[str]) -> list[Chunk]:
    available = chunks_from_raw(config.RAW_DIR)
    missing = [chunk_id for chunk_id in ids if chunk_id not in available]
    if missing:
        raise KeyError(", ".join(missing))
    return [available[chunk_id] for chunk_id in ids]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ask", description="노동법 질문에 근거 조문과 함께 답한다")
    parser.add_argument("question")
    parser.add_argument(
        "--chunks",
        help="개발용. 검색 대신 쓸 청크 id를 쉼표로 구분한다. 예: '근로기준법 제26조,근로기준법 시행령 별표 1'",
    )
    args = parser.parse_args(argv)

    if args.chunks:
        ids = [chunk_id.strip() for chunk_id in args.chunks.split(",") if chunk_id.strip()]
        try:
            chunks = load_chunks(ids)
        except KeyError as error:
            print(f"data/raw에 없는 청크 id: {error.args[0]}", file=sys.stderr)
            return 1
    else:
        try:
            chunks = search(args.question, config.TOP_K)
        except NotImplementedError:
            print("search가 아직 구현되지 않았다. --chunks로 청크 id를 지정하라.", file=sys.stderr)
            return 1

    try:
        result, stats = answer_with_stats(args.question, chunks)
    except httpx.HTTPError as error:
        print(f"Ollama 호출이 재시도 후에도 실패했다: {type(error).__name__}", file=sys.stderr)
        return 1
    print(result.text)
    if stats:
        print(
            f"[{config.CHAT_MODEL}] {stats.seconds:.1f}초, prompt_eval_count {stats.prompt_eval_count}",
            file=sys.stderr,
        )
    return 0
