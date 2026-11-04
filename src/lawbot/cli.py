import argparse
import sys

import httpx

from lawbot import config
from lawbot.answer import answer_with_stats
from lawbot.search import get_chunks, search


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
        chunks = get_chunks(ids)
        found = {chunk.id for chunk in chunks}
        missing = [chunk_id for chunk_id in ids if chunk_id not in found]
        if missing:
            print(f"색인에 없는 청크 id: {', '.join(missing)}", file=sys.stderr)
            return 1
    else:
        chunks = search(args.question, config.TOP_K)

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
