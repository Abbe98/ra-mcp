"""In-process ``Client`` tests for the search_mpo tool's signatur/ID lookup."""

from pathlib import Path

import lancedb
import pytest
from fastmcp import Client

from ra_mcp_diplomatics_lib.ingest import ingest_mpo
from ra_mcp_diplomatics_mcp import diplomatics_mcp


MPO_FIXTURE = Path(__file__).parents[3] / "libs" / "diplomatics-lib" / "tests" / "fixtures" / "mpo_sample.csv"


@pytest.fixture
def mpo_db(tmp_path, monkeypatch):
    """Point the tool at a LanceDB built from the diplomatics-lib MPO sample (fragments 1-5)."""
    uri = str(tmp_path / "diplomatics.lance")
    ingest_mpo(lancedb.connect(uri), MPO_FIXTURE)
    monkeypatch.setattr("ra_mcp_diplomatics_mcp.mpo_tool.LANCEDB_URI", uri)
    return uri


async def _search(**params) -> str:
    async with Client(diplomatics_mcp) as client:
        result = await client.call_tool("search_mpo", {"offset": 0, **params})
    return result.content[0].text


@pytest.mark.parametrize("keyword", ["Fr 3", "MPO 3", "fr. 3"])
async def test_search_mpo_tool_resolves_explicit_signature(mpo_db, keyword):
    text = await _search(keyword=keyword)
    assert f"MPO results for '{keyword}': showing 1 of 1" in text
    assert "**MPO 3** (signatur Fr 3, exact match)" in text
    assert "Collection: Östergötlands handlingar" in text


async def test_search_mpo_tool_bare_number_pins_fragment_first(mpo_db):
    text = await _search(keyword="1")
    assert "'1' is also an MPO fragment signatur (Fr 1)" in text
    table_rows = [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| MPO ")]
    assert table_rows[0].startswith("| 1 |")
    assert len(table_rows) > 1


async def test_search_mpo_tool_unknown_explicit_signature(mpo_db):
    text = await _search(keyword="Fr 999")
    assert text.startswith("No MPO fragment with signatur 'Fr 999' (MPO ID 999) found")


async def test_search_mpo_tool_description_documents_signature_lookup():
    async with Client(diplomatics_mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    tool = tools["search_mpo"]
    assert "Fr 6000" in (tool.description or "")
    assert "Fr 6000" in tool.inputSchema["properties"]["keyword"]["description"]
