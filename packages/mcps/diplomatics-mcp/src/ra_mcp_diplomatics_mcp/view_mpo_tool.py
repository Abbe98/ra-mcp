"""MCP tool for viewing a single MPO parchment fragment in the document viewer."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import uuid4

from fastmcp import Context, FastMCP
from fastmcp.apps import UI_EXTENSION_ID, AppConfig
from fastmcp.tools import ToolResult
from mcp import types
from pydantic import Field

from ra_mcp_common.telemetry import mark_span_error
from ra_mcp_dataset_lib import get_lancedb
from ra_mcp_diplomatics_lib import DiplomaticsSearch
from ra_mcp_diplomatics_lib.config import LANCEDB_URI
from ra_mcp_diplomatics_lib.identifiers import format_mpo_signature, parse_mpo_id
from ra_mcp_viewer_mcp.formatter import build_summary, error_result
from ra_mcp_viewer_mcp.models import ViewerState
from ra_mcp_viewer_mcp.resolve import manifest_resolve_document
from ra_mcp_viewer_mcp.state import put_state
from ra_mcp_viewer_mcp.tools import RESOURCE_URI

from .formatter import format_mpo_info


logger = logging.getLogger("ra_mcp.diplomatics.view_mpo")


def register_view_mpo_tool(mcp: FastMCP) -> None:
    """Register the view_mpo MCP tool."""

    @mcp.tool(
        name="view_mpo",
        tags={"diplomatics", "mpo", "viewer"},
        annotations={"readOnlyHint": True, "openWorldHint": True},
        description=(
            "View an MPO parchment fragment in the document viewer with full codicological metadata. "
            "Takes an MPO fragment id — 'Fr 6000', '6000', 'R1006000' or a bildvisning/IIIF URL all work — "
            "and opens the interactive viewer "
            "with the fragment images and a metadata panel showing manuscript type, dating, "
            "script, material, content, decoration, and damage descriptions."
        ),
        app=AppConfig(resource_uri=RESOURCE_URI),  # AppConfig: pydantic populate_by_name
    )
    async def view_mpo(
        mpo_id: Annotated[
            int | str, Field(description="MPO fragment id/signatur — 'Fr 6000', 6000, 'MPO 6000', 'R1006000', or a bildvisning/IIIF manifest URL.")
        ],
        ctx: Context,
        highlight_term: Annotated[str | None, Field(description="Optional search term to highlight.")] = None,
        max_pages: Annotated[int, Field(description="Maximum pages to load.", ge=1, le=20)] = 20,
    ) -> ToolResult:
        """Look up MPO record and open in viewer with full metadata."""
        fragment_id = parse_mpo_id(mpo_id)
        if fragment_id is None:
            mark_span_error(f"unparseable MPO id: {mpo_id}", error_type="validation")
            return error_result(f"Could not read '{mpo_id}' as an MPO fragment id. Use 'Fr 6000', 6000, 'R1006000', or a bildvisning/IIIF URL.")
        signature = format_mpo_signature(fragment_id)

        try:
            db = get_lancedb(LANCEDB_URI)
            searcher = DiplomaticsSearch(db)
            row = searcher.get_mpo_by_id(fragment_id)
        except Exception as exc:
            logger.error("view_mpo: DB lookup failed: %s", exc, exc_info=True)
            mark_span_error(f"Error looking up MPO {signature}: {exc}")
            return error_result(f"Error looking up MPO {signature}: {exc}")

        if row is None:
            mark_span_error(f"MPO {signature} not found", error_type="validation")
            return error_result(f"MPO {signature} not found.")

        manifest_url = row.get("manifest_url", "")
        if not manifest_url:
            mark_span_error(f"MPO {signature} has no IIIF manifest — no images available")
            return error_result(f"MPO {signature} has no IIIF manifest — no images available. The record metadata is:\n\n{format_mpo_info(row)}")

        try:
            resolved = await manifest_resolve_document(manifest_url, max_pages)
        except (ValueError, LookupError) as exc:
            mark_span_error(str(exc))
            return error_result(str(exc))
        except Exception as exc:
            logger.error("view_mpo: manifest resolution failed: %s", exc, exc_info=True)
            mark_span_error(f"Error resolving manifest: {exc}")
            return error_result(f"Error resolving manifest: {exc}")

        document_info = format_mpo_info(row)

        has_ui = ctx.client_supports_extension(UI_EXTENSION_ID)
        summary = build_summary(
            len(resolved.image_urls),
            resolved.page_numbers,
            has_ui,
            resolved.image_urls,
        )

        view_id = str(uuid4())
        state = ViewerState(
            view_id=view_id,
            image_urls=resolved.image_urls,
            text_layer_urls=resolved.text_layer_urls,
            page_numbers=resolved.page_numbers,
            document_info=document_info,
            highlight_term=highlight_term or "",
            reference_code=signature,
        )
        sc = await put_state(state)

        logger.info("view_mpo: MPO %s, %d page(s), view_id=%s", signature, len(resolved.image_urls), view_id)
        return ToolResult(
            content=[types.TextContent(type="text", text=summary)],
            structured_content=sc,
        )
