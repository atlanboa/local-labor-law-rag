import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from dotenv import dotenv_values

API_URL = "http://www.law.go.kr/DRF/lawService.do"
ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
RAW_DIR = ROOT / "data" / "raw"

LAWS = {
    "labor-standards-act": "근로기준법",
    "labor-standards-decree": "근로기준법 시행령",
    "minimum-wage-act": "최저임금법",
    "retirement-benefit-act": "근로자퇴직급여 보장법",
    # Middle dot is U+318D, not U+00B7; normalize_title accepts either in responses.
    "gender-equality-act": "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률",
}
THD_CMP_KINDS = (1, 2)


class CollectError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RawResponse:
    filename: str
    law: str
    params: dict[str, str]
    body: bytes


def fetch(client: httpx.Client, oc: str, filename: str, law: str, params: dict[str, str]) -> RawResponse:
    # httpx exceptions from raise_for_status quote the URL, which carries the key.
    response = client.get(API_URL, params={"OC": oc, "type": "JSON", **params})
    if response.status_code != 200:
        raise CollectError(f"{filename}: HTTP {response.status_code}")

    body = response.content
    if oc.encode() in body:
        raise CollectError(f"{filename}: 응답 원본에 인증키가 들어 있어 저장하지 않았다")
    try:
        parsed = json.loads(body)
    except ValueError as error:
        raise CollectError(f"{filename}: JSON이 아닌 응답") from error
    if not isinstance(parsed, dict) or "result" in parsed:
        message = parsed.get("result") if isinstance(parsed, dict) else "객체가 아닌 응답"
        raise CollectError(f"{filename}: API 오류: {message}")
    return RawResponse(filename, law, params, body)


def normalize_title(title: str) -> str:
    return title.replace("·", "ㆍ").replace(" ", "")


def parse_law_id(raw: RawResponse) -> str:
    try:
        info = json.loads(raw.body)["법령"]["기본정보"]
        title, law_id = info["법령명_한글"], info["법령ID"]
    except (KeyError, TypeError) as error:
        raise CollectError(f"{raw.filename}: 기본정보를 찾지 못했다") from error
    if normalize_title(title) != normalize_title(raw.law):
        raise CollectError(f"{raw.filename}: {raw.law}를 요청했는데 {title}가 왔다")
    return law_id


def fetch_all(client: httpx.Client, oc: str) -> list[RawResponse]:
    responses = []
    for slug, law in LAWS.items():
        law_response = fetch(client, oc, f"{slug}.law.json", law, {"target": "law", "LM": law})
        law_id = parse_law_id(law_response)
        responses.append(law_response)
        for kind in THD_CMP_KINDS:
            params = {"target": "thdCmp", "knd": str(kind), "ID": law_id}
            responses.append(fetch(client, oc, f"{slug}.thdCmp-knd{kind}.json", law, params))
    return responses


def write_raw(responses: list[RawResponse], out_dir: Path, collected_at: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for raw in responses:
        (out_dir / raw.filename).write_bytes(raw.body)
        files.append(
            {
                "file": raw.filename,
                "law": raw.law,
                "params": raw.params,
                "sha256": hashlib.sha256(raw.body).hexdigest(),
            }
        )
    manifest = {"api": API_URL, "collected_at": collected_at, "files": files}
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    oc = dotenv_values(ENV_PATH).get("LAW_API_OC")
    if not oc:
        print(f"LAW_API_OC가 {ENV_PATH}에 없거나 비어 있다", file=sys.stderr)
        return 1
    try:
        with httpx.Client(timeout=60) as client:
            # Fetch everything first so a failed run leaves earlier raw files intact.
            responses = fetch_all(client, oc)
    except CollectError as error:
        print(error, file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(f"요청 실패: {type(error).__name__}", file=sys.stderr)
        return 1
    write_raw(responses, RAW_DIR, date.today().isoformat())
    print(f"{len(responses)}개 응답을 {RAW_DIR}에 저장했다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
