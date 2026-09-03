"""MCP tool for searching MPO medieval parchment fragments."""

from __future__ import annotations

import logging
import re
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from ra_mcp_common.telemetry import mark_span_error
from ra_mcp_dataset_lib import SearchResult, get_lancedb, require_keyword
from ra_mcp_diplomatics_lib import DiplomaticsSearch
from ra_mcp_diplomatics_lib.config import LANCEDB_URI

from .formatter import format_mpo_results


logger = logging.getLogger("ra_mcp.diplomatics.mpo_tool")

# The catalogue cites every fragment as "Fr N" (Fr 1-Fr 11804 from the MPO
# project, Fr 20000-Fr 31903 from the older CCM catalogue) but the id column holds
# the bare number, so "Fr 6000" would otherwise reach full-text search as two
# meaningless tokens and the one record the user asked for is the one they cannot
# find. Matches "Fr 6000", "fr6000", "Fr. 6000", "MPO 6000" and a bare "6000".
_SIGNATURE_RE = re.compile(r"^(?:mpo[\s.:-]*)?(?:fr[\s.:-]*)?(\d+)$", re.IGNORECASE)


def _fragment_id(keyword: str) -> int | None:
    """Return the fragment id a keyword names, or None if it names no fragment."""
    match = _SIGNATURE_RE.match(keyword.strip())
    return int(match[1]) if match else None


def register_mpo_tool(mcp: FastMCP) -> None:
    """Register the search_mpo MCP tool with the given FastMCP server."""

    @mcp.tool(
        name="search_mpo",
        tags={"diplomatics", "mpo", "search"},
        annotations={"readOnlyHint": True, "openWorldHint": True},
        description=(
            "Search MPO (Medeltida Pergamentomslag) — 23,000+ medieval parchment fragments used as bookbinding covers. "
            "Fragments are cited as 'Fr N' — pass a signature straight through as the keyword "
            "('Fr 6000', 'MPO 6000', or a bare '6000') to look up that exact fragment. "
            "Returns results as a markdown table with key columns (ID, category, dating, origin, script, content). "
            "ALWAYS present search results to the user as a table — do not convert to prose. "
            "Each result includes a IIIF manifest URL for viewing fragment images — pass this to view_manifest. "
            "Paginate with offset (0, 25, 50, ...)."
        ),
    )
    def search_mpo(
        keyword: Annotated[
            str,
            Field(
                description=(
                    "Search term for full-text search across MPO fragment text. "
                    "A catalogue signature such as 'Fr 6000' (or a bare '6000') is resolved to that exact fragment."
                )
            ),
        ],
        offset: Annotated[
            int,
            Field(description="Pagination start position. Use 0 for first page, then 25, 50, etc."),
        ] = 0,
        limit: Annotated[
            int,
            Field(description="Maximum number of records to return per query (default 25)."),
        ] = 25,
        category: Annotated[
            str | None,
            Field(description="Optional filter: only return fragments in this category (case-insensitive substring match)."),
        ] = None,
        institution: Annotated[
            str | None,
            Field(description="Optional filter: only return fragments held at this institution (case-insensitive substring match)."),
        ] = None,
        script: Annotated[
            str | None,
            Field(description="Optional filter: only return fragments with this script type (case-insensitive substring match)."),
        ] = None,
        research_context: Annotated[
            str | None,
            Field(description="Brief summary of the user's research goal. Used for logging only."),
        ] = None,
    ) -> str:
        """Search MPO medieval parchment fragment corpus using full-text search."""
        if err := require_keyword(keyword, "'liturgy'"):
            return err

        if research_context:
            logger.info("search_mpo | context: %s", research_context)
        logger.info("search_mpo called with keyword='%s', offset=%d, limit=%d", keyword, offset, limit)

        try:
            db = get_lancedb(LANCEDB_URI)
            searcher = DiplomaticsSearch(db)

            # Resolve a signature to a point lookup before searching any text. Only on
            # the first page: the hit is a single record, so re-showing it under every
            # offset would make paging report the same fragment forever.
            fragment_id = _fragment_id(keyword) if offset == 0 else None
            if fragment_id is not None and (row := searcher.get_mpo_by_id(fragment_id)) is not None:
                return format_mpo_results(SearchResult(records=[row], total_hits=1, keyword=keyword, offset=0, limit=limit))

            result = searcher.search_mpo(
                keyword,
                limit=limit,
                offset=offset,
                category=category,
                institution=institution,
                script=script,
            )
            return format_mpo_results(result)

        except Exception as exc:
            logger.error("search_mpo failed: %s: %s", type(exc).__name__, exc, exc_info=True)
            mark_span_error(f"MPO search failed: {exc!s}")
            return f"Error: MPO search failed — {exc!s}"
