"""Tests for the MPO search-result formatter, in particular exact signatur matches."""

from ra_mcp_dataset_lib import SearchResult
from ra_mcp_diplomatics_mcp.formatter import format_mpo_results


def _mpo(mpo_id: int, **fields) -> dict:
    rec = {
        "id": mpo_id,
        "category": "Lit",
        "dating": "14. Jh.",
        "origin_place": "Schweden",
        "script": "Textualis",
        "content": "1r-2v Ordo missae.",
    }
    rec.update(fields)
    return rec


def _result(keyword: str, records: list[dict], *, total: int | None = None, offset: int = 0, limit: int = 25) -> SearchResult:
    return SearchResult(records=records, total_hits=len(records) if total is None else total, keyword=keyword, offset=offset, limit=limit)


def test_format_mpo_results_plain_keyword_has_no_exact_match_note():
    out = format_mpo_results(_result("Missale", [_mpo(7)]))
    assert "MPO results for 'Missale': showing 1 of 1" in out
    assert "exact match" not in out.lower()
    assert "| 7 | Lit | 14. Jh. | Schweden | Textualis | 1r-2v Ordo missae. |" in out


def test_format_mpo_results_explicit_signature_marks_exact_match_with_details():
    row = _mpo(
        6000, institution="RA", collection="Östergötlands handlingar", volume_signature="1539:2:1          1539:2:1", ra_number="5121.04", material="Pergament"
    )
    out = format_mpo_results(_result("Fr 6000", [row]))
    assert "Exact match: 'Fr 6000' is the signatur of MPO fragment 6000 (Fr 6000)." in out
    assert "**MPO 6000** (signatur Fr 6000, exact match)" in out
    assert "Institution: RA" in out
    assert "Collection: Östergötlands handlingar" in out
    assert "Volume signature: 1539:2:1 1539:2:1" in out  # padded source whitespace collapsed
    assert "RA number: 5121.04" in out
    assert "Material: Pergament" in out
    assert "More results available" not in out


def test_format_mpo_results_bare_number_explains_pinned_row():
    out = format_mpo_results(_result("1", [_mpo(1), _mpo(4)]))
    assert "'1' is also an MPO fragment signatur (Fr 1): that fragment is listed first, followed by full-text hits for '1'." in out
    assert "**MPO 1** (signatur Fr 1, exact match)" in out
    assert "**MPO 4**" not in out  # ordinary short-content hit gets no detail block


def test_format_mpo_results_bare_number_without_exact_row_is_plain_search():
    # No fragment 999 exists: the lib fell back to full-text search and the first row is an ordinary hit.
    out = format_mpo_results(_result("999", [_mpo(4)]))
    assert "signatur" not in out
    assert "exact match" not in out.lower()


def test_format_mpo_results_explicit_signature_not_found_message():
    out = format_mpo_results(_result("Fr 999", []))
    assert out.startswith("No MPO fragment with signatur 'Fr 999' (MPO ID 999) found")
    assert "filters" in out


def test_format_mpo_results_bare_number_not_found_is_generic_message():
    assert format_mpo_results(_result("999", [])) == "No MPO results found for '999'."


def test_format_mpo_results_signature_past_end_reports_offset():
    out = format_mpo_results(_result("Fr 3", [], total=1, offset=1))
    assert out == "No more MPO results for 'Fr 3' at offset 1. Total found: 1"
