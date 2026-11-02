import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from dotenv import dotenv_values

API_URL = "https://www.law.go.kr/DRF/lawService.do"
SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
RAW_DIR = ROOT / "data" / "raw"


@dataclass(frozen=True, slots=True)
class LawSpec:
    name: str
    collect_thd_cmp: bool


LAWS = {
    "labor-standards-act": LawSpec("근로기준법", True),
    # Decree thdCmp adds nothing: knd1 answers for the parent act, knd2 for an unrelated law.
    "labor-standards-decree": LawSpec("근로기준법 시행령", False),
    "minimum-wage-act": LawSpec("최저임금법", True),
    "retirement-benefit-act": LawSpec("근로자퇴직급여 보장법", True),
    # Middle dot is U+318D, not U+00B7; normalize_title accepts either in responses.
    "gender-equality-act": LawSpec("남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률", True),
}
THD_CMP_SERVICES = {1: "ThdCmpLawXService", 2: "LspttnThdCmpLawXService"}


class CollectError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RawResponse:
    filename: str
    law: str
    params: dict[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class LawVersion:
    mst: str
    effective_date: str


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


def find_current_version(client: httpx.Client, oc: str, law: str, today: str) -> LawVersion:
    # Not stored: search responses embed the key in their detail links.
    params = {"OC": oc, "type": "JSON", "target": "eflaw", "query": law, "nw": "3", "display": "100"}
    response = client.get(SEARCH_URL, params=params)
    if response.status_code != 200:
        raise CollectError(f"{law}: 검색 HTTP {response.status_code}")
    try:
        items = response.json()["LawSearch"]["law"]
        # A single search hit comes back as an object, not a list.
        items = items if isinstance(items, list) else [items]
        current = [
            LawVersion(item["법령일련번호"], item["시행일자"])
            for item in items
            if normalize_title(item["법령명한글"]) == normalize_title(law) and item["현행연혁코드"] == "현행"
        ]
    except (ValueError, KeyError, TypeError) as error:
        raise CollectError(f"{law}: 검색 응답을 해석하지 못했다") from error
    if len(current) != 1:
        raise CollectError(f"{law}: 현행 법령을 하나로 특정하지 못했다({len(current)}건)")
    if current[0].effective_date > today:
        raise CollectError(f"{law}: 현행 시행일자 {current[0].effective_date}가 오늘 이후다")
    return current[0]


def parse_law_id(raw: RawResponse) -> str:
    try:
        info = json.loads(raw.body)["법령"]["기본정보"]
        title, law_id, effective_date = info["법령명_한글"], info["법령ID"], info["시행일자"]
    except (KeyError, TypeError) as error:
        raise CollectError(f"{raw.filename}: 기본정보를 찾지 못했다") from error
    if normalize_title(title) != normalize_title(raw.law):
        raise CollectError(f"{raw.filename}: {raw.law}를 요청했는데 {title}가 왔다")
    if effective_date != raw.params["efYd"]:
        raise CollectError(f"{raw.filename}: 시행일자 {raw.params['efYd']}를 요청했는데 {effective_date}가 왔다")
    if not isinstance(law_id, str):
        raise CollectError(f"{raw.filename}: 법령ID가 문자열이 아니다")
    return law_id


def check_thd_cmp_law_id(raw: RawResponse, service: str, law_id: str) -> None:
    try:
        actual = json.loads(raw.body)[service]["기본정보"]["법령ID"]
    except (KeyError, TypeError) as error:
        raise CollectError(f"{raw.filename}: 법령ID를 찾지 못했다") from error
    if actual != law_id:
        raise CollectError(f"{raw.filename}: 법령ID {law_id}를 요청했는데 {actual!r}가 왔다")


def fetch_all(client: httpx.Client, oc: str, today: str) -> list[RawResponse]:
    responses = []
    for slug, spec in LAWS.items():
        version = find_current_version(client, oc, spec.name, today)
        params = {"target": "eflaw", "MST": version.mst, "efYd": version.effective_date}
        body = fetch(client, oc, f"{slug}.law.json", spec.name, params)
        law_id = parse_law_id(body)
        responses.append(body)
        if not spec.collect_thd_cmp:
            continue
        for kind, service in THD_CMP_SERVICES.items():
            params = {"target": "thdCmp", "knd": str(kind), "ID": law_id}
            thd_cmp = fetch(client, oc, f"{slug}.thdCmp-knd{kind}.json", spec.name, params)
            check_thd_cmp_law_id(thd_cmp, service, law_id)
            responses.append(thd_cmp)
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
    article_effective_dates = {
        raw.law: json.loads(raw.body)["법령"]["기본정보"].get("조문시행일자문자열")
        for raw in responses
        if raw.params["target"] == "eflaw"
    }
    manifest = {
        "api": API_URL,
        "collected_at": collected_at,
        "article_effective_dates": article_effective_dates,
        "files": files,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    oc = dotenv_values(ENV_PATH).get("LAW_API_OC")
    if not oc:
        print(f"LAW_API_OC가 {ENV_PATH}에 없거나 비어 있다", file=sys.stderr)
        return 1
    today = date.today()
    try:
        with httpx.Client(timeout=60) as client:
            # Fetch everything first so a failed run leaves earlier raw files intact.
            responses = fetch_all(client, oc, today.strftime("%Y%m%d"))
    except CollectError as error:
        print(error, file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(f"요청 실패: {type(error).__name__}", file=sys.stderr)
        return 1
    write_raw(responses, RAW_DIR, today.isoformat())
    print(f"{len(responses)}개 응답을 {RAW_DIR}에 저장했다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
