import json

import httpx
import pytest

from lawbot import collect

KEY = "fake-test-key"
LAW_IDS = {spec.name: f"{index:06d}" for index, spec in enumerate(collect.LAWS.values(), start=1)}
DECREE = "근로기준법 시행령"
EFFECTIVE_DATE = "20200101"


def search_item(title, serial):
    link = f"/DRF/lawService.do?OC={KEY}"
    return {"법령명한글": title, "법령일련번호": serial, "시행일자": EFFECTIVE_DATE, "법령상세링크": link}


def search_body(law):
    item = search_item(law, LAW_IDS[law])
    # The real API answers the decree's single hit with an object and the others with a list.
    items = item if law == DECREE else [search_item(f"{law} 시행규칙", "999999"), item]
    return json.dumps({"LawSearch": {"law": items}}, ensure_ascii=False).encode()


def law_body(law, dates="20991231:제1조"):
    info = {"법령명_한글": law, "법령ID": LAW_IDS[law], "조문시행일자문자열": dates}
    return json.dumps({"법령": {"기본정보": info}}, ensure_ascii=False).encode()


def thd_cmp_body(kind, law_id):
    return json.dumps({collect.THD_CMP_SERVICES[kind]: {"기본정보": {"법령ID": law_id}}}).encode()


class FakeApi:
    def __init__(self):
        self.requests = []
        self.thd_cmp = {}

    def __call__(self, request):
        self.requests.append(request)
        params = request.url.params
        if request.url.path.endswith("lawSearch.do"):
            return httpx.Response(200, content=search_body(params["query"]))
        if params["target"] == "eflaw":
            law = next(law for law, law_id in LAW_IDS.items() if law_id == params["MST"])
            return httpx.Response(200, content=law_body(law))
        kind = int(params["knd"])
        body = self.thd_cmp.get((params["ID"], kind), thd_cmp_body(kind, params["ID"]))
        return httpx.Response(200, content=body)


@pytest.fixture
def api(monkeypatch, tmp_path):
    fake = FakeApi()
    real_client = httpx.Client
    monkeypatch.setattr(
        collect.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake), **kwargs)
    )
    env = tmp_path / ".env"
    env.write_text(f"LAW_API_OC={KEY}\n", encoding="utf-8")
    monkeypatch.setattr(collect, "ENV_PATH", env)
    monkeypatch.setattr(collect, "RAW_DIR", tmp_path / "raw")
    return fake


def seed_raw_files():
    collect.RAW_DIR.mkdir()
    existing = collect.RAW_DIR / "labor-standards-act.law.json"
    existing.write_bytes(b"previous run")
    return existing


def test_collects_each_law_at_its_current_effective_version(api):
    assert collect.main() == 0

    assert all(request.url.scheme == "https" for request in api.requests)
    eflaw = [r.url for r in api.requests if r.url.path.endswith("lawService.do") and r.url.params["target"] == "eflaw"]
    assert sorted(url.params["MST"] for url in eflaw) == sorted(LAW_IDS.values())
    assert {url.params["efYd"] for url in eflaw} == {EFFECTIVE_DATE}


def test_decree_is_collected_as_eflaw_body_without_thd_cmp(api):
    assert collect.main() == 0

    service_params = [r.url.params for r in api.requests if r.url.path.endswith("lawService.do")]
    decree_id = LAW_IDS[DECREE]
    decree_targets = [p["target"] for p in service_params if decree_id in (p.get("MST"), p.get("ID"))]
    assert decree_targets == ["eflaw"]
    saved = {path.name for path in collect.RAW_DIR.glob("labor-standards-decree.*")}
    assert saved == {"labor-standards-decree.law.json"}


def test_manifest_records_article_dates_per_law_with_lf_endings(api):
    assert collect.main() == 0

    raw_manifest = (collect.RAW_DIR / "manifest.json").read_bytes()
    assert b"\r" not in raw_manifest
    assert json.loads(raw_manifest)["article_effective_dates"] == {law: "20991231:제1조" for law in LAW_IDS}


def test_saved_files_do_not_contain_the_key(api):
    assert collect.main() == 0

    assert all(KEY.encode() not in path.read_bytes() for path in collect.RAW_DIR.iterdir())


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"{}", id="empty-object"),
        pytest.param(b"", id="missing-law-empty-body"),
        pytest.param(thd_cmp_body(1, "999999"), id="other-law"),
        pytest.param(thd_cmp_body(1, None), id="null-id"),
        pytest.param(thd_cmp_body(1, 1), id="non-string-id"),
        pytest.param(thd_cmp_body(1, [LAW_IDS["근로기준법"]]), id="list-id"),
        pytest.param(json.dumps({"ThdCmpLawXService": {"기본정보": {}}}).encode(), id="no-id"),
    ],
)
def test_bad_thd_cmp_response_keeps_existing_raw_files(api, capsys, body):
    existing = seed_raw_files()
    api.thd_cmp[(LAW_IDS["근로기준법"], 1)] = body

    assert collect.main() == 1

    assert existing.read_bytes() == b"previous run"
    assert KEY not in capsys.readouterr().err


def test_thd_cmp_knd2_is_checked_against_its_own_service(api):
    existing = seed_raw_files()
    api.thd_cmp[(LAW_IDS["근로기준법"], 2)] = thd_cmp_body(1, LAW_IDS["근로기준법"])

    assert collect.main() == 1

    assert existing.read_bytes() == b"previous run"

