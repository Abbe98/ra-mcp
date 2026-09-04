"""Tests for DiplomaticsSearch over ingested SDHK and MPO sample data."""

from pathlib import Path

import lancedb
import pytest

from ra_mcp_diplomatics_lib.ingest import ingest_mpo, ingest_sdhk
from ra_mcp_diplomatics_lib.search_operations import DiplomaticsSearch, MPOSignature, format_mpo_signature, parse_mpo_signature


FIXTURES = Path(__file__).parent / "fixtures"
SDHK_FIXTURE = FIXTURES / "sdhk_sample.csv"
MPO_FIXTURE = FIXTURES / "mpo_sample.csv"


@pytest.fixture
def search(tmp_path):
    """Return a DiplomaticsSearch backed by ingested sample data."""
    db = lancedb.connect(str(tmp_path / "test.lance"))
    ingest_sdhk(db, SDHK_FIXTURE)
    ingest_mpo(db, MPO_FIXTURE)
    return DiplomaticsSearch(db)


def test_search_sdhk_returns_results(search):
    result = search.search_sdhk("Kung")
    assert result.total_hits >= 1
    assert len(result.records) >= 1


def test_search_sdhk_empty_keyword_returns_error(search):
    with pytest.raises(ValueError):
        search.search_sdhk("")


def test_search_sdhk_whitespace_keyword_returns_error(search):
    with pytest.raises(ValueError):
        search.search_sdhk("   ")


def test_search_sdhk_pagination(search):
    result = search.search_sdhk("Kung", limit=2)
    assert len(result.records) <= 2
    assert result.limit == 2


def test_search_mpo_returns_results(search):
    result = search.search_mpo("Missale")
    assert result.total_hits >= 1
    assert len(result.records) >= 1


def test_search_mpo_empty_keyword_returns_error(search):
    with pytest.raises(ValueError):
        search.search_mpo("")


def test_search_result_has_manifest_url(search):
    result = search.search_sdhk("Kung")
    assert result.records
    assert "manifest_url" in result.records[0]


def test_search_result_fields(search):
    result = search.search_sdhk("Kung")
    assert result.keyword == "Kung"
    assert result.offset == 0
    assert result.limit == 25


def test_search_mpo_result_has_manifest_url(search):
    result = search.search_mpo("Missale")
    assert result.records
    assert "manifest_url" in result.records[0]


# --- MPO signatur ("Fr 6000") parsing --------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        pytest.param("6000", MPOSignature(6000, explicit=False), id="bare-number"),
        pytest.param("  6000  ", MPOSignature(6000, explicit=False), id="bare-number-padded"),
        pytest.param("#6000", MPOSignature(6000, explicit=False), id="hash-number"),
        pytest.param("Fr 6000", MPOSignature(6000, explicit=True), id="fr-space"),
        pytest.param("Fr. 6000", MPOSignature(6000, explicit=True), id="fr-dot"),
        pytest.param("fr6000", MPOSignature(6000, explicit=True), id="fr-no-space-lowercase"),
        pytest.param("FR 6000", MPOSignature(6000, explicit=True), id="fr-uppercase"),
        pytest.param("Fragm. 6000", MPOSignature(6000, explicit=True), id="fragm-dot"),
        pytest.param("Fragment 6000", MPOSignature(6000, explicit=True), id="fragment-word"),
        pytest.param("Fr nr 6000", MPOSignature(6000, explicit=True), id="fr-nr"),
        pytest.param("MPO 6000", MPOSignature(6000, explicit=True), id="mpo-space"),
        pytest.param("MPO nr. 6000", MPOSignature(6000, explicit=True), id="mpo-nr-dot"),
        pytest.param("mpo6000", MPOSignature(6000, explicit=True), id="mpo-no-space"),
        pytest.param("Fr 1", MPOSignature(1, explicit=True), id="single-digit"),
    ],
)
def test_parse_mpo_signature_recognises_fragment_numbers(text, expected):
    assert parse_mpo_signature(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="blank"),
        pytest.param("Missale", id="word"),
        pytest.param("Fr", id="prefix-only"),
        pytest.param("6000 Missale", id="number-then-word"),
        pytest.param("Missale 6000", id="word-then-number"),
        pytest.param("1539:2:1", id="volume-signature"),
        pytest.param("14. Jh.", id="dating"),
        pytest.param("Fr 6000-6005", id="range"),
        pytest.param("Fr 6000 6001", id="two-numbers"),
        pytest.param("Frx 6000", id="unknown-prefix"),
        pytest.param("1234567", id="too-many-digits"),
        pytest.param("SDHK 6000", id="sdhk-prefix"),
    ],
)
def test_parse_mpo_signature_rejects_free_text(text):
    assert parse_mpo_signature(text) is None


def test_format_mpo_signature_uses_fr_citation_form():
    assert format_mpo_signature(6000) == "Fr 6000"


# --- search_mpo: exact lookup by signatur -----------------------------------------
# The MPO fixture holds fragments 1-5. A bare "1" also full-text matches other
# rows (a "1" token in their text), which is what the pinned-first-row behaviour
# is for; "3", "4" and "5" have no full-text hits at all.


@pytest.mark.parametrize("keyword", ["Fr 3", "Fr. 3", "fr3", "MPO 3", "Fragment 3"])
def test_search_mpo_explicit_signature_returns_only_that_fragment(search, keyword):
    result = search.search_mpo(keyword)
    assert result.total_hits == 1
    assert [r["id"] for r in result.records] == [3]
    assert result.keyword == keyword


def test_search_mpo_explicit_signature_unknown_id_returns_nothing(search):
    result = search.search_mpo("Fr 999")
    assert result.total_hits == 0
    assert result.records == []


def test_search_mpo_explicit_signature_past_first_page_is_empty(search):
    result = search.search_mpo("Fr 3", offset=1)
    assert result.total_hits == 1
    assert result.records == []


def test_search_mpo_explicit_signature_respects_filters(search):
    # Fragment 3 is category "Theol": found within that filter, not within "Lit".
    assert [r["id"] for r in search.search_mpo("Fr 3", category="theol").records] == [3]
    assert search.search_mpo("Fr 3", category="Lit").records == []


def test_search_mpo_bare_number_returns_exact_fragment_when_no_text_hits(search):
    result = search.search_mpo("3")
    assert result.total_hits == 1
    assert [r["id"] for r in result.records] == [3]


def test_search_mpo_bare_number_pins_exact_fragment_before_text_hits(search):
    text_hits = search.search_mpo("Fr 1")  # sanity: fragment 1 exists
    assert text_hits.total_hits == 1
    result = search.search_mpo("1")
    ids = [r["id"] for r in result.records]
    assert ids[0] == 1
    assert len(ids) > 1, "fixture should give full-text hits for '1' beyond fragment 1"
    assert ids.count(1) == 1, "the pinned fragment must not be duplicated by the full-text hits"
    assert result.total_hits == len(ids)


def test_search_mpo_bare_number_pagination_is_gap_free(search):
    full = [r["id"] for r in search.search_mpo("1", limit=25).records]
    paged: list[int] = []
    for offset in range(len(full)):
        page = search.search_mpo("1", limit=1, offset=offset)
        assert page.total_hits == len(full)
        paged += [r["id"] for r in page.records]
    assert paged == full
    two_per_page = [r["id"] for r in search.search_mpo("1", limit=2).records] + [r["id"] for r in search.search_mpo("1", limit=2, offset=2).records]
    assert two_per_page == full[:4]


def test_search_mpo_bare_number_past_end_is_empty(search):
    total = search.search_mpo("1").total_hits
    result = search.search_mpo("1", offset=total)
    assert result.records == []
    assert result.total_hits == total


def test_search_mpo_bare_number_unknown_id_falls_back_to_text_search(search):
    # No fragment 999, so this is a plain full-text search (which finds nothing here).
    result = search.search_mpo("999")
    assert result.total_hits == 0
    assert result.records == []


def test_search_mpo_bare_number_filtered_out_falls_back_to_text_search(search):
    # Fragment 1 is "Lit"; asking for "Theol" drops the pin and leaves the text hits.
    result = search.search_mpo("1", category="theol")
    ids = [r["id"] for r in result.records]
    assert 1 not in ids
    assert all(r["category"] == "Theol" for r in result.records)


@pytest.mark.parametrize("kwargs", [{"offset": -1}, {"limit": 0}])
def test_search_mpo_signature_rejects_bad_paging(search, kwargs):
    with pytest.raises(ValueError):
        search.search_mpo("Fr 3", **kwargs)
