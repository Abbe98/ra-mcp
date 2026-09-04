"""Tests for DiplomaticsSearch over ingested SDHK and MPO sample data."""

from pathlib import Path

import lancedb
import pytest

from ra_mcp_diplomatics_lib.ingest import ingest_mpo, ingest_sdhk
from ra_mcp_diplomatics_lib.search_operations import DiplomaticsSearch


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


def test_search_mpo_signature_filter_matches_volume_signature(search):
    result = search.search_mpo(signature="1539:3:1")
    assert [rec["id"] for rec in result.records] == [2]


def test_search_mpo_signature_filter_matches_ra_number(search):
    result = search.search_mpo(signature="5121.04")
    assert result.total_hits == 5


def test_search_mpo_signature_filter_narrows_keyword_search(search):
    unfiltered = search.search_mpo("Pergament")
    filtered = search.search_mpo("Pergament", signature="1539:3:1")
    assert filtered.total_hits < unfiltered.total_hits
    assert all(rec["id"] == 2 for rec in filtered.records)


def test_search_mpo_filter_only_requires_no_keyword(search):
    result = search.search_mpo(category="Theol")
    assert result.total_hits == 2
    assert {rec["id"] for rec in result.records} == {2, 3}


def test_search_mpo_filter_only_paginates(search):
    first = search.search_mpo(institution="KA", limit=2, offset=0)
    second = search.search_mpo(institution="KA", limit=2, offset=2)
    assert first.total_hits == 5
    assert second.total_hits == 5
    assert len(first.records) == 2
    assert {rec["id"] for rec in first.records}.isdisjoint({rec["id"] for rec in second.records})


def test_search_mpo_without_keyword_or_filter_raises(search):
    with pytest.raises(ValueError):
        search.search_mpo()


def test_search_mpo_blank_keyword_without_filter_raises(search):
    with pytest.raises(ValueError):
        search.search_mpo("   ")


def test_search_mpo_signature_matches_indexed_fragment_number(search):
    """The 'Fr <id>' signature is indexed, so it is findable by full-text search too."""
    result = search.search_mpo("Fr 4")
    assert 4 in {rec["id"] for rec in result.records}
