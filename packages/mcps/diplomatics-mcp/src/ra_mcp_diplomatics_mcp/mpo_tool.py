"""MCP tool for searching MPO medieval parchment fragments."""

from __future__ import annotations

import logging
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from ra_mcp_common.telemetry import mark_span_error
from ra_mcp_dataset_lib import get_lancedb
from ra_mcp_diplomatics_lib import DiplomaticsSearch
from ra_mcp_diplomatics_lib.config import LANCEDB_URI
from ra_mcp_diplomatics_lib.identifiers import format_mpo_signature, parse_mpo_ids, parse_mpo_reference

from .formatter import format_mpo_lookup, format_mpo_results


logger = logging.getLogger("ra_mcp.diplomatics.mpo_tool")

# Repeated in the error paths so a caller that gets the id form wrong is told the
# accepted shapes rather than just "invalid".
ACCEPTED_ID_FORMS = "'Fr 6000', '6000', 'MPO 6000', 'R1006000', a bildvisning/IIIF URL, or a comma-separated list of those"


def _lookup(searcher: DiplomaticsSearch, ids: list[int], note: str = "") -> str:
    """Fetch fragments by id and render the exact-lookup block."""
    rows = searcher.get_mpo_by_ids(ids)
    return format_mpo_lookup(rows, ids, note=note)


def register_mpo_tool(mcp: FastMCP) -> None:
    """Register the search_mpo MCP tool with the given FastMCP server."""

    @mcp.tool(
        name="search_mpo",
        tags={"diplomatics", "mpo", "search"},
        annotations={"readOnlyHint": True, "openWorldHint": True},
        description=(
            "Search MPO (Medeltida Pergamentomslag) — 23,000+ medieval parchment fragments used as bookbinding covers. "
            "Three ways to query, combinable: (1) keyword — ranked full-text search over the German codicological descriptions; "
            "(2) mpo_id — exact lookup of one or more fragments by their number; (3) signature — substring match on shelf marks "
            "(RA number, CCM signum, volume signature, collection). Filters: category, institution, script. "
            "IDS: every fragment has a number that Riksarkivet writes as a signature, 'Fr 6000' for fragment 6000. "
            "When the user names a fragment — 'Fr 6000', 'MPO 6000', a bare '6000', or a bildvisning/IIIF URL — pass it as "
            "mpo_id to get that exact record; several at once with 'Fr 6000, Fr 6001'. A bare number passed as the keyword is "
            "also tried as a fragment id, and both the exact match and the full-text hits are returned. "
            "Returns results as a markdown table with key columns (Fragment, category, dating, origin, script, content). "
            "ALWAYS present search results to the user as a table — do not convert to prose. "
            "Each result includes a IIIF manifest URL for viewing fragment images — pass this to view_manifest. "
            "Paginate with offset (0, 25, 50, ...)."
        ),
    )
    def search_mpo(
        keyword: Annotated[
            str | None,
            Field(description="Search term for full-text search across MPO fragment text. Optional if mpo_id or a filter is given."),
        ] = None,
        mpo_id: Annotated[
            str | None,
            Field(
                description=(
                    "Exact fragment lookup by MPO id/signatur. Accepts 'Fr 6000', '6000', 'MPO 6000', "
                    "the ARKIS image id 'R1006000', a bildvisning or IIIF manifest URL, or a NAD reference code. "
                    "Several at once: 'Fr 6000, Fr 6001'."
                )
            ),
        ] = None,
        signature: Annotated[
            str | None,
            Field(
                description=(
                    "Filter on the fragment's shelf marks — RA number (e.g. '5121.04'), CCM signum, "
                    "volume signature (e.g. '1539:2:1') or collection name (case-insensitive substring). "
                    "For the fragment's own number use mpo_id instead."
                )
            ),
        ] = None,
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
        """Search the MPO parchment fragment corpus by full text, fragment id, or shelf mark."""
        has_filter = any((signature, category, institution, script))
        keyword = keyword.strip() if keyword else ""

        if not keyword and not mpo_id and not has_filter:
            mark_span_error("no MPO query given", error_type="validation")
            return (
                "Error: give at least one of keyword, mpo_id or a filter (signature, category, institution, script). "
                f"For a keyword search try 'liturgy'; for an exact fragment use mpo_id={ACCEPTED_ID_FORMS}."
            )

        if research_context:
            logger.info("search_mpo | context: %s", research_context)
        logger.info("search_mpo called with keyword='%s', mpo_id='%s', signature='%s', offset=%d, limit=%d", keyword, mpo_id, signature, offset, limit)

        try:
            db = get_lancedb(LANCEDB_URI)
            searcher = DiplomaticsSearch(db)

            # 1. An explicit id request wins: the caller named specific fragments.
            if mpo_id:
                ids, unparsed = parse_mpo_ids(mpo_id)
                if not ids:
                    mark_span_error(f"unparseable mpo_id: {mpo_id}", error_type="validation")
                    return f"Error: could not read '{mpo_id}' as an MPO fragment id. Accepted forms: {ACCEPTED_ID_FORMS}."
                note = f"Ignored, not an MPO id: {', '.join(unparsed)}." if unparsed else ""
                return _lookup(searcher, ids, note)

            # 2. The keyword may itself name a fragment. "Fr 6000" / "R1006000" is
            #    unambiguous, so answer with the record. A bare "6000" might be an id
            #    or might be text to search (a year, a shelf mark), so do both and let
            #    the caller see the exact match alongside the full-text hits.
            reference = parse_mpo_reference(keyword) if keyword and not has_filter else None
            if reference and reference.explicit:
                return _lookup(searcher, [reference.id], f"Read '{keyword}' as MPO fragment {format_mpo_signature(reference.id)}.")

            result = searcher.search_mpo(
                keyword or None,
                limit=limit,
                offset=offset,
                category=category,
                institution=institution,
                script=script,
                signature=signature,
            )
            body = format_mpo_results(result, query_label=_query_label(keyword, signature, category, institution, script))

            if reference and offset == 0:
                exact = searcher.get_mpo_by_id(reference.id)
                if exact:
                    note = f"'{keyword}' also reads as a fragment id, so the exact record is shown first. Full-text matches follow."
                    return f"{format_mpo_lookup([exact], [reference.id], note=note)}\n\n---\n\n{body}"

            return body

        except ValueError as exc:
            mark_span_error(str(exc), error_type="validation")
            return f"Error: {exc!s}"
        except Exception as exc:
            logger.error("search_mpo failed: %s: %s", type(exc).__name__, exc, exc_info=True)
            mark_span_error(f"MPO search failed: {exc!s}")
            return f"Error: MPO search failed — {exc!s}"


def _query_label(keyword: str, signature: str | None, category: str | None, institution: str | None, script: str | None) -> str:
    """Describe the query for the result header.

    A filter-only search has no keyword to quote, so the filters name it instead —
    otherwise the header would read "results for ''".
    """
    if keyword:
        return f"'{keyword}'"
    parts = [
        f"{label}='{value}'" for label, value in (("signature", signature), ("category", category), ("institution", institution), ("script", script)) if value
    ]
    return " + ".join(parts) if parts else "(no query)"
