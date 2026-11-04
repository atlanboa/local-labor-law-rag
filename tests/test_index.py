import json
from collections import Counter

import pytest

from lawbot import config, index

ACT = "근로기준법"
DECREE = "근로기준법 시행령"


@pytest.fixture(scope="module")
def corpus():
    return index.build_chunks(config.RAW_DIR)


@pytest.fixture(scope="module")
def chunks(corpus):
    return {chunk.id: chunk for chunk in corpus.chunks}


def raw_units(slug):
    return json.loads((config.RAW_DIR / f"{slug}.law.json").read_text(encoding="utf-8"))["법령"]["조문"]["조문단위"]


def test_one_chunk_per_article_and_appendix_without_chapter_rows(corpus):
    counts = Counter(chunk.law for chunk in corpus.chunks)
    articles = [unit for unit in raw_units("labor-standards-act") if unit["조문여부"] == "조문"]

    assert counts[ACT] == len(articles) + 1
    assert counts[DECREE] == 80 + 7
    assert len({chunk.id for chunk in corpus.chunks}) == len(corpus.chunks)
    assert not any("제1장" in chunk.text.split("\n")[0] for chunk in corpus.chunks)


def test_every_eval_answer_key_is_a_chunk_id(chunks):
    keys = {key for line in config.QUESTIONS_PATH.open(encoding="utf-8") for key in json.loads(line)["required"]}
    assert keys <= chunks.keys()


def test_article_ids_use_law_name_and_branch_number(chunks):
    assert "근로기준법 제43조의2" in chunks
    assert "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률 제19조" in chunks
    assert chunks["근로기준법 제43조의2"].article == "제43조의2"


def test_article_text_joins_paragraphs_items_and_subitems_in_order(chunks):
    text = chunks["근로기준법 제11조"].text

    assert text.startswith("근로기준법 제11조(적용 범위)\n① 이 법은 상시 5명 이상")
    assert text.index("①") < text.index("②") < text.index("③")
    decree_article = next(c for c in chunks.values() if c.law == DECREE and "가." in c.text)
    assert decree_article.text.index("1.") < decree_article.text.index("가.")


def test_appendix_chunk_has_title_then_table(chunks):
    appendix = chunks["근로기준법 시행령 별표 1"]

    assert appendix.text.startswith(
        "근로기준법 시행령 별표 1 상시 4명 이하의 근로자를 사용하는 사업 또는 사업장에 적용하는 법 규정(제7조 관련)\n"
    )
    assert "제1장 총칙" in appendix.text
    assert "근로기준법 별표" in chunks


def test_act_and_decree_articles_link_both_ways(chunks):
    assert {"근로기준법 시행령 제7조", "근로기준법 시행령 제7조의2"} <= set(chunks["근로기준법 제11조"].refs)
    assert "근로기준법 제11조" in chunks["근로기준법 시행령 제7조"].refs


def test_article_links_to_appendix_named_in_its_text(chunks):
    assert "근로기준법 시행령 별표 1" in chunks["근로기준법 시행령 제7조"].refs
    assert "근로기준법 시행령 제7조" in chunks["근로기준법 시행령 별표 1"].refs
    assert "근로기준법 별표" in chunks["근로기준법 제80조"].refs


def test_every_ref_points_into_the_corpus(corpus, chunks):
    assert all(ref in chunks for chunk in corpus.chunks for ref in chunk.refs)


def test_links_outside_the_corpus_are_counted(corpus):
    # No 최저임금법 시행령 or any 시행규칙 was collected.
    assert corpus.dropped_links["최저임금법"] > 0
    assert corpus.dropped_links[ACT] > 0
    assert corpus.dropped_links[DECREE] == 0


def test_pending_dates_attach_to_the_article_of_an_item_entry(chunks):
    assert chunks["근로기준법 제13조"].pending_effective_dates == ("20261208",)
    assert chunks["근로기준법 제110조"].pending_effective_dates == ("20261208",)
    assert chunks["근로기준법 제116조"].pending_effective_dates == ("20261208", "20270101")
    assert chunks["근로기준법 제11조"].pending_effective_dates == ()


def test_dates_come_from_law_info_and_manifest(chunks):
    assert chunks["근로기준법 제11조"].effective_date == "20261008"
    assert chunks["근로기준법 시행령 별표 1"].effective_date == "20251023"
    assert {chunk.collected_at for chunk in chunks.values()} == {"2026-11-02"}


def test_parse_pending_splits_dates_without_separator():
    parsed = index.parse_pending("20261208:제13조,제110조제1호20270101:제44조의4,제13조")

    assert parsed == {"제13조": ["20261208", "20270101"], "제110조": ["20261208"], "제44조의4": ["20270101"]}
