"""Tests for single-record lookup by ID."""

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


def test_get_sdhk_by_id_found(search):
    row = search.get_sdhk_by_id(1)
    assert row is not None
    assert row["id"] == 1


def test_get_sdhk_by_id_not_found(search):
    row = search.get_sdhk_by_id(99999)
    assert row is None


def test_get_mpo_by_id_found(search):
    row = search.get_mpo_by_id(1)
    assert row is not None
    assert row["id"] == 1


def test_get_mpo_by_id_not_found(search):
    row = search.get_mpo_by_id(99999)
    assert row is None


@pytest.mark.parametrize(
    "reference",
    [
        pytest.param(1, id="int"),
        pytest.param("1", id="numeric-string"),
        pytest.param("Fr 1", id="signature"),
        pytest.param("MPO 1", id="mpo-prefix"),
        pytest.param("R1000001", id="arkis-image-id"),
        pytest.param("https://sok.riksarkivet.se/bildvisning/R1000001", id="bildvisning-url"),
        pytest.param("SE/RA/80001/Nr 1-1000/1", id="nad-reference-code"),
    ],
)
def test_get_mpo_by_id_accepts_written_forms(search, reference):
    row = search.get_mpo_by_id(reference)
    assert row is not None
    assert row["id"] == 1


def test_get_mpo_by_id_returns_none_for_non_reference(search):
    assert search.get_mpo_by_id("Missale") is None


def test_get_mpo_by_ids_returns_records_in_requested_order(search):
    rows = search.get_mpo_by_ids(["Fr 3", 1, "R1000002"])
    assert [row["id"] for row in rows] == [3, 1, 2]


def test_get_mpo_by_ids_omits_missing_and_unparseable(search):
    rows = search.get_mpo_by_ids(["Fr 2", "Fr 99999", "Missale"])
    assert [row["id"] for row in rows] == [2]


def test_get_mpo_by_ids_empty_input(search):
    assert search.get_mpo_by_ids([]) == []
