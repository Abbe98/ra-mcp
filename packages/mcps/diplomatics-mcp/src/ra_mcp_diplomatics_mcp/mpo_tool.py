"""MCP tool for searching MPO medieval parchment fragments."""

from __future__ import annotations

import logging
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from ra_mcp_common.telemetry import mark_span_error
from ra_mcp_dataset_lib import get_lancedb, require_keyword
from ra_mcp_diplomatics_lib import DiplomaticsSearch
from ra_mcp_diplomatics_lib.config import LANCEDB_URI

from .formatter import format_mpo_results


logger = logging.getLogger("ra_mcp.diplomatics.mpo_tool")


def register_mpo_tool(mcp: FastMCP) -> None:
    """Register the search_mpo MCP tool with the given FastMCP server."""

    @mcp.tool(
        name="search_mpo",
        tags={"diplomatics", "mpo", "search"},
        annotations={"readOnlyHint": True, "openWorldHint": True},
        description=(
            "Search MPO (Medeltida Pergamentomslag) — 23,000+ medieval parchment fragments used as bookbinding covers. "
            "Also looks up a fragment by its signatur/ID: MPO fragments are cited as 'Fr <number>' (e.g. 'Fr 6000'), "
            "and the number is the MPO ID. A keyword of 'Fr 6000', 'MPO 6000' or just '6000' returns that exact fragment "
            "(a bare number additionally returns full-text hits for the number after the exact match). "
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
                    "Search term for full-text search across MPO fragment text, or a fragment signatur/ID "
                    "for an exact lookup: 'Fr 6000', 'MPO 6000' or '6000' all resolve to MPO fragment 6000."
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
        """Search MPO fragments by full text, or look one up by signatur/ID ("Fr 6000", "6000")."""
        if err := require_keyword(keyword, "'liturgy' or a fragment signatur like 'Fr 6000'"):
            return err

        if research_context:
            logger.info("search_mpo | context: %s", research_context)
        logger.info("search_mpo called with keyword='%s', offset=%d, limit=%d", keyword, offset, limit)

        try:
            db = get_lancedb(LANCEDB_URI)
            searcher = DiplomaticsSearch(db)
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
