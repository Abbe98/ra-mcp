"""In-process ``Client`` tests for the search_mpo tool.

Exercises the tool against a real (tiny) LanceDB built from the sample CSV, so
the id-parsing, exact-lookup and filter paths are tested through the same MCP
surface a client sees.
"""

from pathlib import Path

import lancedb
import pytest
from fastmcp import Client

from ra_mcp_diplomatics_lib.ingest import ingest_mpo, ingest_sdhk
from ra_mcp_diplomatics_mcp import diplomatics_mcp, mpo_tool


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def mpo_db(tmp_path, monkeypatch):
    """Point the tool at a temporary LanceDB holding the sample fragments (ids 1-5)."""
    uri = str(tmp_path / "diplomatics.lance")
    db = lancedb.connect(uri)
    ingest_mpo(db, FIXTURES / "mpo_sample.csv")
    monkeypatch.setattr(mpo_tool, "LANCEDB_URI", uri)
    return uri


async def call(**kwargs) -> str:
    async with Client(diplomatics_mcp) as client:
        result = await client.call_tool("search_mpo", kwargs)
    return result.content[0].text


@pytest.mark.parametrize(
    "reference",
    [
        pytest.param("Fr 1", id="signature"),
        pytest.param("1", id="bare-number"),
        pytest.param("MPO 1", id="mpo-prefix"),
        pytest.param("R1000001", id="arkis-image-id"),
        pytest.param("https://sok.riksarkivet.se/bildvisning/R1000001", id="bildvisning-url"),
    ],
)
async def test_mpo_id_returns_the_exact_fragment(reference):
    text = await call(mpo_id=reference)
    assert "Fr 1" in text
    assert "exact lookup" in text.lower()


async def test_mpo_id_accepts_several_fragments():
    text = await call(mpo_id="Fr 3, Fr 1")
    assert "Fr 3, Fr 1" in text
    # Requested order is preserved in the result table.
    assert text.index("| Fr 3 |") < text.index("| Fr 1 |")


async def test_mpo_id_reports_ids_that_match_no_record():
    text = await call(mpo_id="Fr 1, Fr 99999")
    assert "Not found: Fr 99999" in text
    assert "Fr 1" in text


async def test_mpo_id_with_no_matches_explains_rather_than_returning_nothing():
    text = await call(mpo_id="Fr 99999")
    assert "No MPO fragment found for Fr 99999" in text


async def test_mpo_id_rejects_a_reference_it_cannot_read():
    text = await call(mpo_id="Missale")
    assert text.startswith("Error:")
    assert "Fr 6000" in text


async def test_explicit_signature_as_keyword_is_read_as_an_id():
    text = await call(keyword="Fr 2")
    assert "Read 'Fr 2' as MPO fragment Fr 2." in text
    assert "| Fr 2 |" in text


async def test_bare_number_keyword_returns_exact_match_and_full_text_hits():
    text = await call(keyword="2")
    assert "also reads as a fragment id" in text
    assert "| Fr 2 |" in text


async def test_bare_number_keyword_with_no_such_fragment_falls_back_to_search():
    text = await call(keyword="99999")
    assert "also reads as a fragment id" not in text
    assert "No MPO results found" in text


async def test_keyword_search_still_works():
    text = await call(keyword="Missale")
    assert "MPO results for 'Missale'" in text
    assert "| Fr 1 |" in text


async def test_signature_filter_without_a_keyword():
    text = await call(signature="1539:3:1")
    assert "signature='1539:3:1'" in text
    assert "| Fr 2 |" in text
    assert "| Fr 1 |" not in text


async def test_filter_only_search_without_a_keyword():
    text = await call(category="Theol")
    assert "category='Theol'" in text
    assert "showing 2 of 2" in text


async def test_no_query_at_all_is_an_actionable_error():
    text = await call()
    assert text.startswith("Error:")
    assert "mpo_id" in text


async def test_results_teach_the_signature_convention():
    text = await call(keyword="Missale")
    assert "'Fr 6000'" in text


async def test_details_include_shelf_marks_and_bildvisning():
    text = await call(mpo_id="Fr 1")
    assert "RA number: 5121.04" in text
    assert "Volume signature: 1539:2:1" in text
    assert "Bildvisning: https://sok.riksarkivet.se/bildvisning/R1000001" in text


async def test_search_mpo_schema_advertises_the_id_parameter():
    async with Client(diplomatics_mcp) as client:
        tools = await client.list_tools()
    schema = next(t for t in tools if t.name == "search_mpo").inputSchema
    assert "mpo_id" in schema["properties"]
    assert "signature" in schema["properties"]
    # Every parameter is optional now that an id or a filter is a complete query.
    assert not schema.get("required")


def test_sdhk_ingest_is_unaffected(tmp_path):
    """Guard the shared ingest path: the MPO changes must not alter SDHK's schema."""
    db = lancedb.connect(str(tmp_path / "sdhk.lance"))
    table = ingest_sdhk(db, Path(__file__).parents[3] / "libs/diplomatics-lib/tests/fixtures/sdhk_sample.csv")
    assert "signature" not in table.schema.names
