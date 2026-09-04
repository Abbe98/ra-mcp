"""Plain-text formatter for SDHK and MPO search results."""

from __future__ import annotations

from typing import Any

from ra_mcp_diplomatics_lib.identifiers import format_mpo_signature, mpo_bildvisning_url
from ra_mcp_diplomatics_lib.search_operations import SearchResult


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding '…' if needed."""
    if not text:
        return ""
    return text[:max_len] + "…" if len(text) > max_len else text


def _escape_pipe(text: str) -> str:
    """Escape pipe characters and newlines for markdown table cells."""
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def format_sdhk_results(result: SearchResult) -> str:
    """Format SDHK search results as a markdown table for MCP/LLM consumption.

    Args:
        result: SearchResult from DiplomaticsSearch.search_sdhk.

    Returns:
        Markdown-formatted table string.
    """
    if not result.records:
        if result.offset > 0:
            return f"No more SDHK results for '{result.keyword}' at offset {result.offset}. Total found: {result.total_hits}"
        return f"No SDHK results found for '{result.keyword}'."

    lines: list[str] = []
    lines.append(f"SDHK results for '{result.keyword}': showing {len(result.records)} of {result.total_hits} (offset {result.offset})")
    lines.append("")
    lines.append("PRESENT THESE RESULTS AS A TABLE.")
    lines.append("")

    # Table header
    lines.append("| SDHK | Date | Place | Author | Summary | Status |")
    lines.append("|------|------|-------|--------|---------|--------|")

    for rec in result.records:
        sdhk_id = rec.get("id", "")
        date = _escape_pipe(rec.get("date", "") or "")
        place = _escape_pipe(rec.get("place", "") or "")
        author = _escape_pipe(rec.get("author", "") or "")
        summary = _escape_pipe(_truncate(rec.get("summary", "") or "", 120))

        manifest_url = rec.get("manifest_url", "")
        has_transcription = rec.get("has_transcription", False)
        if manifest_url:
            status = "Digitized + Transcribed" if has_transcription else "Digitized"
        else:
            status = "Not digitized"

        lines.append(f"| {sdhk_id} | {date} | {place} | {author} | {summary} | {status} |")

    lines.append("")

    # Detail blocks for records with summaries/editions
    has_details = False
    for rec in result.records:
        summary = rec.get("summary", "") or ""
        edition = rec.get("edition", "") or ""
        manifest_url = rec.get("manifest_url", "")
        if len(summary) > 120 or edition or manifest_url:
            if not has_details:
                lines.append("### Details")
                lines.append("")
                has_details = True
            sdhk_id = rec.get("id", "")
            lines.append(f"**SDHK {sdhk_id}**")
            if summary:
                lines.append(f"Summary: {_truncate(summary, 500)}")
            if edition:
                lines.append(f"Edition: {_truncate(edition, 300)}")
            if manifest_url:
                lines.append(f"IIIF Manifest: {manifest_url}")
            lines.append("")

    # Pagination info
    next_offset = result.offset + result.limit
    if next_offset < result.total_hits:
        lines.append(f"More results available. Use offset={next_offset} to see the next page.")

    return "\n".join(lines)


# Shown with every MPO result set so the caller (and the user reading it) learns
# that the numeric id *is* the fragment signature and how to hand it back.
MPO_ID_HINT = "Fragment ids are MPO signatures — fragment 6000 is cited as 'Fr 6000'. To fetch one exactly, pass mpo_id='Fr 6000' (or 6000)."


def _mpo_signature(rec: dict[str, Any]) -> str:
    """Canonical 'Fr <id>' signature for a record, derived from its id.

    Derived rather than read from the stored ``signature`` column so records from
    a dataset snapshot ingested before that column existed still render correctly.
    """
    mpo_id = rec.get("id")
    if isinstance(mpo_id, int):
        return format_mpo_signature(mpo_id)
    return str(rec.get("signature", "") or mpo_id or "?")


def _mpo_detail_lines(rec: dict[str, Any], lines: list[str]) -> None:
    """Append the detail block for one MPO record (identifiers, then description)."""
    mpo_id = rec.get("id")
    lines.append(f"**{_mpo_signature(rec)}** (id {mpo_id})")

    for label, key in [
        ("Title", "title"),
        ("Author", "author"),
        ("RA number", "ra_number"),
        ("CCM signum", "ccm_signum"),
        ("Volume signature", "volume_signature"),
        ("Collection", "collection"),
        ("Institution", "institution"),
    ]:
        val = rec.get(key, "") or ""
        if val:
            lines.append(f"{label}: {val}")

    content = rec.get("content", "") or ""
    if content:
        lines.append(f"Content: {_truncate(content, 500)}")

    manifest = rec.get("iiif_manifest", "") or rec.get("manifest_url", "") or ""
    if manifest:
        lines.append(f"IIIF Manifest: {manifest}")

    bildvisning = rec.get("bildvisning_url", "") or ""
    if not bildvisning and isinstance(mpo_id, int):
        bildvisning = mpo_bildvisning_url(mpo_id)
    if bildvisning:
        lines.append(f"Bildvisning: {bildvisning}")

    lines.append("")


def _mpo_table(records: list[dict[str, Any]], lines: list[str]) -> None:
    """Append the markdown summary table for a set of MPO records."""
    lines.append("| Fragment | Category | Dating | Origin | Script | Content |")
    lines.append("|----------|----------|--------|--------|--------|---------|")

    for rec in records:
        signature = _escape_pipe(_mpo_signature(rec))
        category = _escape_pipe(rec.get("category", "") or "")
        dating = _escape_pipe(rec.get("dating", "") or "")
        origin = _escape_pipe(rec.get("origin_place", "") or "")
        script = _escape_pipe(rec.get("script", "") or "")
        content = _escape_pipe(_truncate(rec.get("content", "") or "", 120))

        lines.append(f"| {signature} | {category} | {dating} | {origin} | {script} | {content} |")

    lines.append("")


def format_mpo_results(result: SearchResult, *, query_label: str | None = None) -> str:
    """Format MPO search results as a markdown table for MCP/LLM consumption.

    Args:
        result: SearchResult from DiplomaticsSearch.search_mpo.
        query_label: Human description of the query, used in the header and the
            no-results message. Defaults to the search keyword — needed because a
            filter-only search (by signature or institution) has no keyword to name.

    Returns:
        Markdown-formatted table string.
    """
    label = query_label or f"'{result.keyword}'"

    if not result.records:
        if result.offset > 0:
            return f"No more MPO results for {label} at offset {result.offset}. Total found: {result.total_hits}"
        return f"No MPO results found for {label}."

    lines: list[str] = []
    lines.append(f"MPO results for {label}: showing {len(result.records)} of {result.total_hits} (offset {result.offset})")
    lines.append("")
    lines.append("PRESENT THESE RESULTS AS A TABLE.")
    lines.append(MPO_ID_HINT)
    lines.append("")

    _mpo_table(result.records, lines)

    # Detail blocks for records with longer content or a manifest/title worth citing.
    detailed = [rec for rec in result.records if len(rec.get("content", "") or "") > 120 or rec.get("iiif_manifest") or rec.get("title")]
    if detailed:
        lines.append("### Details")
        lines.append("")
        for rec in detailed:
            _mpo_detail_lines(rec, lines)

    # Pagination info
    next_offset = result.offset + result.limit
    if next_offset < result.total_hits:
        lines.append(f"More results available. Use offset={next_offset} to see the next page.")

    return "\n".join(lines)


def format_mpo_lookup(rows: list[dict[str, Any]], requested: list[int], *, note: str = "") -> str:
    """Format the result of an exact fragment-id lookup.

    Args:
        rows: The records found, in the order the ids were requested.
        requested: The fragment ids that were asked for — so ids that matched no
            record can be named rather than silently dropped.
        note: Optional leading line explaining how the ids were arrived at (e.g.
            that a bare number in the keyword was read as a fragment id).

    Returns:
        Markdown-formatted string.
    """
    signatures = ", ".join(format_mpo_signature(mpo_id) for mpo_id in requested)
    found_ids = {row.get("id") for row in rows}
    missing = [mpo_id for mpo_id in requested if mpo_id not in found_ids]

    lines: list[str] = []
    if note:
        lines.append(note)
    if not rows:
        lines.append(
            f"No MPO fragment found for {signatures}. The MPO corpus holds ~23,000 fragments numbered from 1; check the number, or search by keyword instead."
        )
        return "\n".join(lines)

    lines.append(f"MPO exact lookup for {signatures}: {len(rows)} of {len(requested)} found.")
    lines.append("")
    lines.append("PRESENT THESE RESULTS AS A TABLE.")
    lines.append(MPO_ID_HINT)
    lines.append("")

    _mpo_table(rows, lines)

    lines.append("### Details")
    lines.append("")
    for row in rows:
        _mpo_detail_lines(row, lines)

    if missing:
        lines.append(f"Not found: {', '.join(format_mpo_signature(mpo_id) for mpo_id in missing)}.")

    return "\n".join(lines)


def format_sdhk_info(row: dict[str, Any]) -> str:
    """Format an SDHK record as markdown for the viewer info panel."""
    sdhk_id = row.get("id", "?")
    lines: list[str] = [f"## SDHK {sdhk_id}"]

    title = row.get("title", "")
    if title:
        lines.append(f"*{title}*")
    lines.append("")

    for label, key in [
        ("Author", "author"),
        ("Date", "date"),
        ("Place", "place"),
        ("Language", "language"),
        ("Printed", "printed"),
    ]:
        val = row.get(key, "")
        if val:
            lines.append(f"**{label}:** {val}")

    summary = row.get("summary", "")
    if summary:
        lines.append("")
        lines.append("### Summary")
        lines.append(summary)

    edition = row.get("edition", "")
    if edition:
        truncated = edition[:1000] + "..." if len(edition) > 1000 else edition
        lines.append("")
        lines.append("### Edition")
        lines.append(truncated)

    seals = row.get("seals", "")
    if seals:
        lines.append("")
        lines.append("### Seals")
        lines.append(seals)

    return "\n".join(lines)


def format_mpo_info(row: dict[str, Any]) -> str:
    """Format an MPO record as markdown for the viewer info panel."""
    mpo_id = row.get("id", "?")
    lines: list[str] = [f"## MPO {mpo_id}"]

    manuscript_type = row.get("manuscript_type", "")
    if manuscript_type:
        lines.append(f"*{manuscript_type}*")
    lines.append("")

    lines.append(f"**Signature:** {_mpo_signature(row)}")

    for label, key in [
        ("Type", "manuscript_type"),
        ("RA number", "ra_number"),
        ("CCM signum", "ccm_signum"),
        ("Volume signature", "volume_signature"),
        ("Category", "category"),
        ("Title", "title"),
        ("Author", "author"),
        ("Dating", "dating"),
        ("Origin", "origin_place"),
        ("Institution", "institution"),
        ("Collection", "collection"),
        ("Script", "script"),
        ("Material", "material"),
        ("Notation", "notation"),
        ("Size", "format_size"),
    ]:
        val = row.get(key, "")
        if val:
            lines.append(f"**{label}:** {val}")

    decoration = row.get("decoration", "")
    if decoration:
        lines.append("")
        lines.append("### Decoration")
        lines.append(decoration)

    content = row.get("content", "")
    if content:
        lines.append("")
        lines.append("### Content")
        lines.append(content)

    damage = row.get("damage", "")
    if damage:
        lines.append("")
        lines.append("### Damage")
        lines.append(damage)

    return "\n".join(lines)
