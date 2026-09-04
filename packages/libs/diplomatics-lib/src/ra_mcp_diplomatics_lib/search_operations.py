"""Full-text search operations over SDHK and MPO LanceDB tables."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from ra_mcp_dataset_lib import SearchResult, combine, equals, lancedb_fts_search, not_equals, text_contains

from .config import MPO_TABLE, SDHK_TABLE


if TYPE_CHECKING:
    import lancedb


__all__ = ["DiplomaticsSearch", "MPOSignature", "SearchResult", "format_mpo_signature", "parse_mpo_signature"]


# An MPO fragment is cited by its *signatur* — the fragment number, written
# "Fr 6000" (Fr = fragment) in the literature and in Riksarkivet's own MPO
# database. The number is the table's ``id`` column. This accepts the bare
# number and the common prefixed spellings:
#   "6000", "Fr 6000", "Fr. 6000", "fr6000", "Fragm. 6000", "Fragment 6000",
#   "MPO 6000", "Fr nr 6000", "MPO nr. 6000", "#6000"
# but not free text ("6000 Missale"), volume signatures ("1539:2:1"), dates
# ("14. Jh.") or ranges ("Fr 6000-6005").
_MPO_SIGNATURE_RE = re.compile(
    r"""^\s*
        (?:(?P<prefix>mpo|fr(?:agm(?:ent)?)?)\.?\s*(?:nr\.?\s*)?)?   # optional 'Fr' / 'MPO' [nr]
        \#?\s*
        (?P<number>\d{1,6})
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


class MPOSignature(NamedTuple):
    """A search term recognised as an MPO fragment number (signatur)."""

    id: int
    explicit: bool
    """True when the term carried a 'Fr'/'MPO' prefix and so can only mean this fragment."""


def parse_mpo_signature(text: str) -> MPOSignature | None:
    """Recognise an MPO fragment signatur ("Fr 6000", "MPO 6000", "6000") in ``text``.

    Returns ``None`` when ``text`` is anything other than a single fragment
    number, with or without a ``Fr``/``MPO`` prefix. A bare number is reported
    with ``explicit=False`` because it may equally be a year, a leaf count or a
    volume number that the caller should still full-text search.
    """
    if not text:
        return None
    match = _MPO_SIGNATURE_RE.match(text)
    if match is None:
        return None
    return MPOSignature(id=int(match.group("number")), explicit=match.group("prefix") is not None)


def format_mpo_signature(mpo_id: int) -> str:
    """Render an MPO id in its citation form, e.g. ``6000`` -> ``"Fr 6000"``."""
    return f"Fr {mpo_id}"


class DiplomaticsSearch:
    """Search operations over SDHK and MPO LanceDB tables."""

    def __init__(self, db: lancedb.DBConnection) -> None:
        self._db = db

    def search_sdhk(
        self,
        keyword: str,
        *,
        limit: int = 25,
        offset: int = 0,
        author: str | None = None,
        place: str | None = None,
        language: str | None = None,
    ) -> SearchResult:
        """Search the SDHK table using full-text search.

        Args:
            keyword: Search term (required, non-empty).
            limit: Maximum number of results to return.
            offset: Number of results to skip (for pagination).
            author: Optional filter on the author field (case-insensitive substring).
            place: Optional filter on the place field (case-insensitive substring).
            language: Optional filter on the language field (case-insensitive substring).

        Returns:
            SearchResult with matching records.

        Raises:
            ValueError: If keyword is empty.
        """
        where = combine(
            text_contains("author", author) if author else None,
            text_contains("place", place) if place else None,
            text_contains("language", language) if language else None,
        )
        return lancedb_fts_search(self._db, SDHK_TABLE, keyword, limit=limit, offset=offset, where=where)

    def search_mpo(
        self,
        keyword: str,
        *,
        limit: int = 25,
        offset: int = 0,
        category: str | None = None,
        institution: str | None = None,
        script: str | None = None,
    ) -> SearchResult:
        """Search the MPO table by fragment signatur or full-text search.

        A keyword that is an MPO signatur is resolved to that exact fragment
        (see :func:`parse_mpo_signature`):

        - ``"Fr 6000"`` / ``"MPO 6000"`` (explicit prefix) returns only fragment
          6000 — or no results if there is no such fragment.
        - ``"6000"`` (bare number) returns fragment 6000 pinned as the first
          result, followed by the ordinary full-text hits for ``"6000"`` (the
          number may also be a year, a volume number, ...). If no fragment 6000
          exists it is a plain full-text search.

        The optional filters apply to the exact lookup as well, so a fragment
        outside the requested category/institution/script is not returned.

        Args:
            keyword: Search term or fragment signatur (required, non-empty).
            limit: Maximum number of results to return.
            offset: Number of results to skip (for pagination).
            category: Optional filter on the category field (case-insensitive substring).
            institution: Optional filter on the institution field (case-insensitive substring).
            script: Optional filter on the script field (case-insensitive substring).

        Returns:
            SearchResult with matching records.

        Raises:
            ValueError: If keyword is empty.
        """
        where = combine(
            text_contains("category", category) if category else None,
            text_contains("institution", institution) if institution else None,
            text_contains("script", script) if script else None,
        )
        signature = parse_mpo_signature(keyword)
        if signature is None:
            return lancedb_fts_search(self._db, MPO_TABLE, keyword, limit=limit, offset=offset, where=where)

        # Validate paging exactly as lancedb_fts_search does, so an exact lookup
        # rejects the same bad input instead of silently returning a record.
        if offset < 0:
            raise ValueError(f"offset must be >= 0 (got {offset})")
        if limit < 1:
            raise ValueError(f"limit must be >= 1 (got {limit})")

        exact = self._lookup_mpo(signature.id, where)
        if signature.explicit:
            records = [exact] if exact is not None and offset == 0 else []
            total = 1 if exact is not None else 0
            return SearchResult(records=records, total_hits=total, keyword=keyword, offset=offset, limit=limit)
        if exact is None:
            return lancedb_fts_search(self._db, MPO_TABLE, keyword, limit=limit, offset=offset, where=where)

        # Pin the exact fragment first, then the full-text hits for the bare
        # number (which exclude that fragment, so the pinned row is never
        # duplicated and total_hits is exact). The combined list is
        # [exact, *fts]; slice the requested page out of it.
        rest_where = combine(where, not_equals("id", signature.id))
        rest = lancedb_fts_search(
            self._db,
            MPO_TABLE,
            keyword,
            limit=limit,
            offset=max(offset - 1, 0),
            where=rest_where,
        )
        records = [exact, *rest.records[: limit - 1]] if offset == 0 else rest.records
        return SearchResult(records=records, total_hits=rest.total_hits + 1, keyword=keyword, offset=offset, limit=limit)

    def _lookup_mpo(self, mpo_id: int, where: str | None) -> dict | None:
        """Point lookup of one MPO record by id, optionally within a filter predicate."""
        table = self._db.open_table(MPO_TABLE)
        predicate = combine(equals("id", mpo_id), where)
        rows = table.search().where(predicate).limit(1).to_list()
        return rows[0] if rows else None

    def get_sdhk_by_id(self, sdhk_id: int) -> dict | None:
        """Look up a single SDHK record by ID.

        Returns the record dict or None if not found.
        """
        table = self._db.open_table(SDHK_TABLE)
        rows = table.search().where(f"id = {sdhk_id}").limit(1).to_list()
        return rows[0] if rows else None

    def get_mpo_by_id(self, mpo_id: int) -> dict | None:
        """Look up a single MPO record by ID (fragment signatur).

        Returns the record dict or None if not found.
        """
        return self._lookup_mpo(mpo_id, None)
