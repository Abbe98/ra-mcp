"""Tests for parsing and rendering MPO fragment identifiers."""

import pytest

from ra_mcp_diplomatics_lib.identifiers import (
    format_mpo_signature,
    mpo_bildvisning_url,
    mpo_image_id,
    parse_mpo_id,
    parse_mpo_ids,
    parse_mpo_reference,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        pytest.param("Fr 6000", 6000, id="canonical-signature"),
        pytest.param("fr 6000", 6000, id="lowercase"),
        pytest.param("FR 6000", 6000, id="uppercase"),
        pytest.param("Fr. 6000", 6000, id="abbreviation-dot"),
        pytest.param("Fr6000", 6000, id="no-space"),
        pytest.param("Fr:6000", 6000, id="colon-separator"),
        pytest.param("Fragment 6000", 6000, id="spelled-out"),
        pytest.param("MPO 6000", 6000, id="mpo-prefix"),
        pytest.param("MPO Fr 6000", 6000, id="mpo-and-fr"),
        pytest.param("mpo-6000", 6000, id="mpo-hyphen"),
        pytest.param("#6000", 6000, id="hash"),
        pytest.param("6000", 6000, id="bare-number"),
        pytest.param("  6000  ", 6000, id="surrounding-whitespace"),
        pytest.param(6000, 6000, id="int"),
        pytest.param(1, 1, id="lowest-id"),
        pytest.param("R1006000", 6000, id="arkis-image-id"),
        pytest.param("r1006000", 6000, id="arkis-image-id-lowercase"),
        pytest.param("https://sok.riksarkivet.se/bildvisning/R1006000", 6000, id="bildvisning-url"),
        pytest.param("https://lbiiif.riksarkivet.se/arkis!R1027029/manifest", 27029, id="iiif-manifest-url"),
        pytest.param("SE/RA/80001/Nr 5001-6000/6000", 6000, id="nad-reference-code"),
        pytest.param("SE/RA/80001/Nr 4001-5000/4814", 4814, id="nad-reference-code-other-block"),
    ],
)
def test_parse_mpo_id_accepts_written_forms(value, expected):
    assert parse_mpo_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("Missale", id="search-term"),
        pytest.param("Textualis Rubr", id="multi-word-term"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace"),
        pytest.param(None, id="none"),
        pytest.param(0, id="zero"),
        pytest.param(-5, id="negative"),
        pytest.param(1_000_000, id="above-range"),
        pytest.param("1539:2:1", id="volume-signature"),
        pytest.param("5121.04", id="ra-number"),
        pytest.param(True, id="bool-is-not-an-id"),
    ],
)
def test_parse_mpo_id_rejects_non_references(value):
    assert parse_mpo_id(value) is None


def reference(value):
    """Parse ``value``, failing the test (rather than the assertion below) if it does not."""
    parsed = parse_mpo_reference(value)
    assert parsed is not None, f"expected {value!r} to parse as an MPO reference"
    return parsed


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("Fr 6000", id="signature"),
        pytest.param("MPO 6000", id="mpo-prefix"),
        pytest.param("R1006000", id="arkis-image-id"),
        pytest.param("SE/RA/80001/Nr 5001-6000/6000", id="nad-reference-code"),
        pytest.param(6000, id="int"),
    ],
)
def test_parse_mpo_reference_marks_prefixed_forms_explicit(value):
    assert reference(value).explicit is True


def test_parse_mpo_reference_marks_bare_number_ambiguous():
    """A bare number may be a fragment id or a search term (a year, a count)."""
    parsed = reference("6000")
    assert parsed.id == 6000
    assert parsed.explicit is False


@pytest.mark.parametrize(
    "value,expected",
    [
        pytest.param("Fr 6000, Fr 6001", [6000, 6001], id="comma-separated-signatures"),
        pytest.param("6000,6001", [6000, 6001], id="comma-separated-numbers"),
        pytest.param("6000 6001", [6000, 6001], id="whitespace-separated"),
        pytest.param("Fr 6000 Fr 6001", [6000, 6001], id="whitespace-separated-signatures"),
        pytest.param("6000; 6001", [6000, 6001], id="semicolon-separated"),
        pytest.param("Fr 6000", [6000], id="single-signature-keeps-inner-space"),
        pytest.param("6000, 6000", [6000], id="duplicates-removed"),
        pytest.param("Fr 6001, 6000", [6001, 6000], id="input-order-preserved"),
        pytest.param("", [], id="empty"),
        pytest.param(6000, [6000], id="int"),
    ],
)
def test_parse_mpo_ids(value, expected):
    ids, _ = parse_mpo_ids(value)
    assert ids == expected


def test_parse_mpo_ids_reports_unparsed_tokens():
    ids, unparsed = parse_mpo_ids("Fr 6000, Missale")
    assert ids == [6000]
    assert unparsed == ["Missale"]


def test_parse_mpo_ids_all_unparsed():
    ids, unparsed = parse_mpo_ids("Missale")
    assert ids == []
    assert unparsed == ["Missale"]


def test_format_and_render_helpers():
    assert format_mpo_signature(6000) == "Fr 6000"
    assert mpo_image_id(6000) == "R1006000"
    assert mpo_image_id(1) == "R1000001"
    assert mpo_bildvisning_url(6000) == "https://sok.riksarkivet.se/bildvisning/R1006000"


def test_image_id_round_trips_through_parse():
    for mpo_id in (1, 4814, 6000, 27029):
        assert parse_mpo_id(mpo_image_id(mpo_id)) == mpo_id
