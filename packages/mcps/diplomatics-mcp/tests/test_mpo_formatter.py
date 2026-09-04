"""Tests for the MPO search-result and exact-lookup formatters."""

from ra_mcp_dataset_lib import SearchResult
from ra_mcp_diplomatics_mcp.formatter import format_mpo_lookup, format_mpo_results


def record(mpo_id: int, **overrides) -> dict:
    base = {
        "id": mpo_id,
        "category": "Lit",
        "dating": "14. Jh.",
        "origin_place": "Schweden",
        "script": "Textualis",
        "content": "1r-2v Ordo missae.",
        "title": "Missale Strengnense",
        "ra_number": "5121.04",
        "volume_signature": "1539:2:1",
        "iiif_manifest": f"https://lbiiif.riksarkivet.se/arkis!R100{mpo_id:04d}/manifest",
    }
    return base | overrides


def result(records: list[dict], *, keyword: str = "Missale", total_hits: int | None = None, offset: int = 0, limit: int = 25) -> SearchResult:
    return SearchResult(
        records=records,
        total_hits=len(records) if total_hits is None else total_hits,
        keyword=keyword,
        offset=offset,
        limit=limit,
    )


def test_results_table_shows_the_canonical_signature():
    text = format_mpo_results(result([record(6000)]))
    assert "| Fragment |" in text
    assert "| Fr 6000 |" in text


def test_results_explain_the_signature_convention():
    text = format_mpo_results(result([record(6000)]))
    assert "'Fr 6000'" in text
    assert "mpo_id" in text


def test_results_use_the_query_label_when_there_is_no_keyword():
    text = format_mpo_results(result([record(1)], keyword=""), query_label="signature='1539:2:1'")
    assert "MPO results for signature='1539:2:1'" in text


def test_no_results_message_uses_the_query_label():
    text = format_mpo_results(result([], keyword=""), query_label="category='Theol'")
    assert text == "No MPO results found for category='Theol'."


def test_no_results_past_the_end_reports_the_total():
    text = format_mpo_results(result([], total_hits=42, offset=50))
    assert "No more MPO results for 'Missale' at offset 50" in text
    assert "42" in text


def test_details_carry_the_shelf_marks():
    text = format_mpo_results(result([record(6000)]))
    assert "**Fr 6000** (id 6000)" in text
    assert "RA number: 5121.04" in text
    assert "Volume signature: 1539:2:1" in text


def test_bildvisning_url_is_derived_when_the_column_is_absent():
    text = format_mpo_results(result([record(6000)]))
    assert "Bildvisning: https://sok.riksarkivet.se/bildvisning/R1006000" in text


def test_bildvisning_url_from_the_record_wins():
    text = format_mpo_results(result([record(6000, bildvisning_url="https://example.invalid/x")]))
    assert "Bildvisning: https://example.invalid/x" in text


def test_pagination_footer_appears_only_when_more_remain():
    more = format_mpo_results(result([record(1)], total_hits=100, limit=25))
    assert "Use offset=25" in more
    assert "Use offset=" not in format_mpo_results(result([record(1)]))


def test_lookup_lists_requested_and_missing_signatures():
    text = format_mpo_lookup([record(6000)], [6000, 6001])
    assert "MPO exact lookup for Fr 6000, Fr 6001: 1 of 2 found." in text
    assert "Not found: Fr 6001." in text


def test_lookup_with_no_hits_explains_the_id_space():
    text = format_mpo_lookup([], [99999])
    assert "No MPO fragment found for Fr 99999" in text
    assert "search by keyword" in text


def test_lookup_note_is_shown_first():
    text = format_mpo_lookup([record(6000)], [6000], note="Read '6000' as MPO fragment Fr 6000.")
    assert text.startswith("Read '6000' as MPO fragment Fr 6000.")


def test_lookup_note_is_shown_even_when_nothing_was_found():
    text = format_mpo_lookup([], [6000], note="Read '6000' as MPO fragment Fr 6000.")
    assert text.startswith("Read '6000' as MPO fragment Fr 6000.")
    assert "No MPO fragment found" in text


def test_signature_falls_back_to_a_stored_column_for_a_row_without_an_int_id():
    """A snapshot ingested before the id column was typed still renders."""
    text = format_mpo_results(result([record(1, id="6000", signature="Fr 6000")]))
    assert "| Fr 6000 |" in text
