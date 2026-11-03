import json
import re
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import chromadb
import httpx

from lawbot import config
from lawbot.models import Chunk

CHUNKS_PATH = config.ROOT / "data" / "chunks" / "chunks.jsonl"
EMBED_BATCH = 16

ARTICLE_ID = re.compile(r"^제\d+조(?:의\d+)?")
APPENDIX_MENTION = re.compile(r"별표(?:\s*(\d+)(?:의(\d+))?)?")
PENDING_GROUP = re.compile(r"(\d{8}):(.*?)(?=\d{8}:|$)")


def as_list(value) -> list:
    # The API returns one item as an object and several as a list.
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def article_label(number: str, branch: str) -> str:
    label = f"제{int(number)}조"
    return f"{label}의{int(branch)}" if branch and int(branch) else label


def appendix_label(number: str | None, branch: str | None) -> str:
    # 근로기준법 has a single unnumbered 별표 (별표번호 0000) that its text calls "별표".
    label = f"별표 {int(number)}" if number and int(number) else "별표"
    return f"{label}의{int(branch)}" if branch and int(branch) else label


def article_text(law: str, unit: dict) -> str:
    parts = [unit["조문내용"]]
    for paragraph in as_list(unit.get("항")):
        parts.append(paragraph.get("항내용"))
        for item in as_list(paragraph.get("호")):
            parts.append(item["호내용"])
            parts.extend(sub["목내용"] for sub in as_list(item.get("목")))
    body = "\n".join(part.strip() for part in parts if part and part.strip())
    return f"{law} {body}"


def appendix_text(law: str, label: str, unit: dict) -> str:
    lines = [line.rstrip() for page in unit["별표내용"] for line in as_list(page)]
    return f"{law} {label} {unit['별표제목']}\n" + "\n".join(lines).strip("\n")


def parse_pending(dates: str | None) -> dict[str, list[str]]:
    # "20261208:제13조,제110조제1호20270101:제44조의4" -> {"제13조": ["20261208"], ...}
    pending: dict[str, list[str]] = {}
    for date, items in PENDING_GROUP.findall(dates or ""):
        for item in filter(None, items.split(",")):
            article = ARTICLE_ID.match(item).group()
            if date not in pending.setdefault(article, []):
                pending[article].append(date)
    return {article: sorted(found) for article, found in pending.items()}


def law_links(thd_cmp: dict) -> list[tuple[str, str, str]]:
    # (law article, target law, target article) from one knd1 or knd2 response.
    (service,) = thd_cmp.values()
    info = service["기본정보"]
    body = next(value for key, value in service.items() if key.endswith("삼단비교"))
    links = []
    for row in as_list(body["법률조문"]):
        source = ARTICLE_ID.match(row["조제목"])
        if not source:
            continue
        for kind, list_key in (("시행령", "시행령조문목록"), ("시행규칙", "시행규칙조문목록")):
            targets = as_list(row.get(f"{kind}조문")) + as_list((row.get(list_key) or {}).get(f"{kind}조문"))
            for target in targets:
                article = ARTICLE_ID.match(target.get("조제목") or "")
                target_law = target.get("법령명") or info.get(f"{kind}명")
                if article:
                    links.append((source.group(), target_law, article.group()))
    return links


@dataclass(slots=True)
class Corpus:
    chunks: list[Chunk]
    # Distinct thdCmp links per source law whose end is not in the corpus.
    dropped_links: Counter


def build_chunks(raw_dir: Path) -> Corpus:
    manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
    collected_at = manifest["collected_at"]
    law_files = [entry["file"] for entry in manifest["files"] if entry["params"]["target"] == "eflaw"]

    drafts: dict[str, dict] = {}
    for filename in law_files:
        law_doc = json.loads((raw_dir / filename).read_text(encoding="utf-8"))["법령"]
        info = law_doc["기본정보"]
        law = info["법령명_한글"]
        pending = parse_pending(manifest["article_effective_dates"].get(law))
        common = {"law": law, "effective_date": info["시행일자"], "collected_at": collected_at}
        for unit in as_list(law_doc["조문"]["조문단위"]):
            if unit["조문여부"] != "조문":
                continue
            label = article_label(unit["조문번호"], unit.get("조문가지번호"))
            chunk_id = f"{law} {label}"
            drafts[chunk_id] = common | {
                "id": chunk_id,
                "article": label,
                "title": unit.get("조문제목", ""),
                "text": article_text(law, unit),
                "pending_effective_dates": tuple(pending.get(label, ())),
            }
        for unit in as_list((law_doc.get("별표") or {}).get("별표단위")):
            if unit["별표구분"] != "별표":
                continue
            label = appendix_label(unit["별표번호"], unit.get("별표가지번호"))
            chunk_id = f"{law} {label}"
            drafts[chunk_id] = common | {
                "id": chunk_id,
                "article": label,
                "title": unit["별표제목"],
                "text": appendix_text(law, label, unit),
            }

    edges: set[tuple[str, str]] = set()
    dropped: set[tuple[str, str, str]] = set()
    for entry in manifest["files"]:
        if entry["params"]["target"] != "thdCmp":
            continue
        law = entry["law"]
        thd_cmp = json.loads((raw_dir / entry["file"]).read_text(encoding="utf-8"))
        for source, target_law, target in law_links(thd_cmp):
            pair = (f"{law} {source}", f"{target_law} {target}")
            if pair[0] in drafts and pair[1] in drafts:
                edges.add(pair)
            else:
                dropped.add((law, *pair))
    for chunk_id, draft in drafts.items():
        if not draft["article"].startswith("제"):
            continue
        for number, branch in APPENDIX_MENTION.findall(draft["text"]):
            appendix_id = f"{draft['law']} {appendix_label(number, branch)}"
            if appendix_id in drafts:
                edges.add((chunk_id, appendix_id))

    order = {chunk_id: position for position, chunk_id in enumerate(drafts)}
    refs: dict[str, set[str]] = {}
    for left, right in edges:
        refs.setdefault(left, set()).add(right)
        refs.setdefault(right, set()).add(left)
    chunks = [
        Chunk(**draft, refs=tuple(sorted(refs.get(chunk_id, ()), key=order.__getitem__)))
        for chunk_id, draft in drafts.items()
    ]
    return Corpus(chunks, Counter(law for law, _, _ in dropped))


def embed(texts: Sequence[str]) -> list[list[float]]:
    vectors = []
    with httpx.Client(base_url=config.OLLAMA_URL, timeout=600) as client:
        for start in range(0, len(texts), EMBED_BATCH):
            batch = list(texts[start : start + EMBED_BATCH])
            # Ollama truncates input past 2048 tokens; only 시행령 별표 6 and 7 are that long.
            response = client.post("/api/embed", json={"model": config.EMBED_MODEL, "input": batch})
            response.raise_for_status()
            vectors.extend(response.json()["embeddings"])
    return vectors


def chunk_to_json(chunk: Chunk) -> str:
    return json.dumps(asdict(chunk), ensure_ascii=False)


def chunk_from_json(line: str) -> Chunk:
    data = json.loads(line)
    return Chunk(**data | {"refs": tuple(data["refs"]), "pending_effective_dates": tuple(data["pending_effective_dates"])})


def write_chunks(chunks: list[Chunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(chunk_to_json(chunk) + "\n" for chunk in chunks), encoding="utf-8", newline="\n")


def open_collection(create: bool = False) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    if not create:
        return client.get_collection(config.COLLECTION)
    if config.COLLECTION in {collection.name for collection in client.list_collections()}:
        client.delete_collection(config.COLLECTION)
    return client.create_collection(config.COLLECTION, configuration={"hnsw": {"space": "cosine"}})


def store(chunks: list[Chunk], vectors: list[list[float]]) -> None:
    collection = open_collection(create=True)
    collection.add(
        ids=[chunk.id for chunk in chunks],
        embeddings=vectors,
        documents=[chunk.text for chunk in chunks],
        metadatas=[{"chunk": chunk_to_json(chunk)} for chunk in chunks],
    )


def main() -> int:
    started = time.perf_counter()
    corpus = build_chunks(config.RAW_DIR)
    write_chunks(corpus.chunks, CHUNKS_PATH)
    try:
        vectors = embed([chunk.text for chunk in corpus.chunks])
    except httpx.HTTPError as error:
        print(f"임베딩 실패({config.OLLAMA_URL}, {config.EMBED_MODEL}): {error}", file=sys.stderr)
        return 1
    store(corpus.chunks, vectors)

    per_law = Counter(chunk.law for chunk in corpus.chunks)
    refs = Counter()
    for chunk in corpus.chunks:
        refs[chunk.law] += len(chunk.refs)
    for law, count in per_law.items():
        print(f"{law}: 청크 {count}, refs {refs[law]}, 버린 연결 {corpus.dropped_links[law]}")
    elapsed = time.perf_counter() - started
    print(f"{len(corpus.chunks)}개 청크를 {CHUNKS_PATH}와 {config.COLLECTION}에 저장했다({elapsed:.1f}초)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
