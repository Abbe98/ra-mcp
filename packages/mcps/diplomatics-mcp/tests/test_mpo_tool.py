"""Tests for search_mpo resolving an "Fr N" catalogue signature to one fragment."""

from pathlib import Path

import lancedb
import pytest
from fastmcp import Client, FastMCP

from ra_mcp_diplomatics_lib.ingest import ingest_mpo
from ra_mcp_diplomatics_mcp import mpo_tool


MPO_FIXTURE = Path(__file__).parents[3] / "libs" / "diplomatics-lib" / "tests" / "fixtures" / "mpo_sample.csv"


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A server whose search_mpo reads a LanceDB table built from the sample CSV."""
    uri = str(tmp_path / "diplomatics.lance")
    ingest_mpo(lancedb.connect(uri), MPO_FIXTURE)
    monkeypatch.setattr(mpo_tool, "LANCEDB_URI", uri)

    mcp = FastMCP(name="test-diplomatics")
    mpo_tool.register_mpo_tool(mcp)
    return mcp


async def call(server, **kwargs) -> str:
    async with Client(server) as client:
        result = await client.call_tool("search_mpo", kwargs)
    return result.content[0].text


@pytest.mark.parametrize(
    "keyword",
    [
        pytest.param("Fr 1", id="canonical"),
        pytest.param("fr1", id="no-separator"),
        pytest.param("FR 1", id="uppercase"),
        pytest.param("Fr. 1", id="period-separator"),
        pytest.param("Fr-1", id="hyphen-separator"),
        pytest.param("MPO 1", id="corpus-marker"),
        pytest.param("  Fr 1  ", id="surrounding-whitespace"),
        pytest.param("1", id="bare-number"),
    ],
)
async def test_signature_resolves_to_the_exact_fragment(server, keyword):
    text = await call(server, keyword=keyword)
    assert "showing 1 of 1" in text
    assert "| 1 | Lit |" in text
    # The manifest URL rides along, so the fragment can go straight to view_manifest.
    assert "IIIF Manifest: https://lbiiif.riksarkivet.se/arkis!R1000001/manifest" in text


async def test_unknown_signature_falls_through_to_text_search(server):
    text = await call(server, keyword="Fr 99999")
    assert text == "No MPO results found for 'Fr 99999'."


async def test_ordinary_keyword_still_searches_text(server):
    text = await call(server, keyword="Missale")
    assert "showing 2 of 2" in text


@pytest.mark.parametrize(
    "keyword",
    [
        pytest.param("Missale", id="word"),
        pytest.param("1539:2:1", id="volume-signature"),
        pytest.param("5121.04", id="ra-number"),
        pytest.param("-1", id="negative"),
    ],
)
def test_fragment_id_only_matches_a_signature(keyword):
    assert mpo_tool._fragment_id(keyword) is None


async def test_signature_is_not_repeated_on_later_pages(server):
    # The hit is a single record; paging past it must not keep re-showing it.
    text = await call(server, keyword="Fr 1", offset=25)
    assert "showing 1 of 1" not in text


async def test_empty_keyword_still_errors(server):
    text = await call(server, keyword="")
    assert "must not be empty" in text
