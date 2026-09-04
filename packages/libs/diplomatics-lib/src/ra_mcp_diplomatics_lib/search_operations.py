"""Full-text search operations over SDHK and MPO LanceDB tables."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ra_mcp_dataset_lib import (
    SearchResult,
    any_of,
    combine,
    equals,
    lancedb_filter_search,
    lancedb_fts_search,
    text_contains,
)

from .config import MPO_TABLE, SDHK_TABLE
from .identifiers import parse_mpo_id


if TYPE_CHECKING:
    import lancedb


__all__ = ["DiplomaticsSearch", "SearchResult"]

# The MPO columns that carry a shelf mark / identifier rather than descriptive
# prose. A user searching "by signatur" means one of these (or the fragment
# number itself, which is handled by the id lookups).
MPO_SIGNATURE_COLUMNS = ("ra_number", "ccm_signum", "volume_signature", "collection")


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
        keyword: str | None = None,
        *,
        limit: int = 25,
        offset: int = 0,
        category: str | None = None,
        institution: str | None = None,
        script: str | None = None,
        signature: str | None = None,
    ) -> SearchResult:
        """Search the MPO table by full text, by filters, or by both.

        With a keyword this is a ranked full-text search narrowed by the filters.
        Without one it is a filter-only query — so "every fragment with this RA
        number" or "everything held at this institution" is answerable without
        inventing a search term that would silently re-rank the results.

        Args:
            keyword: Search term. Optional, but at least one of keyword/category/
                institution/script/signature must be given.
            limit: Maximum number of results to return.
            offset: Number of results to skip (for pagination).
            category: Optional filter on the category field (case-insensitive substring).
            institution: Optional filter on the institution field (case-insensitive substring).
            script: Optional filter on the script field (case-insensitive substring).
            signature: Optional filter matching any of the fragment's shelf-mark
                columns — RA number, CCM signum, volume signature or collection
                (case-insensitive substring).

        Returns:
            SearchResult with matching records.

        Raises:
            ValueError: If neither a keyword nor any filter is given.
        """
        where = combine(
            text_contains("category", category) if category else None,
            text_contains("institution", institution) if institution else None,
            text_contains("script", script) if script else None,
            any_of(*(text_contains(column, signature) for column in MPO_SIGNATURE_COLUMNS)) if signature else None,
        )

        if keyword and keyword.strip():
            return lancedb_fts_search(self._db, MPO_TABLE, keyword, limit=limit, offset=offset, where=where)

        if where is None:
            raise ValueError("search_mpo needs a keyword or at least one filter (category, institution, script, signature)")

        return lancedb_filter_search(self._db, MPO_TABLE, where, limit=limit, offset=offset)

    def get_sdhk_by_id(self, sdhk_id: int) -> dict | None:
        """Look up a single SDHK record by ID.

        Returns the record dict or None if not found.
        """
        table = self._db.open_table(SDHK_TABLE)
        rows = table.search().where(equals("id", sdhk_id)).limit(1).to_list()
        return rows[0] if rows else None

    def get_mpo_by_id(self, mpo_id: int | str) -> dict | None:
        """Look up a single MPO record by fragment id.

        Accepts any written form of the id — ``6000``, ``"Fr 6000"``, ``"MPO 6000"``,
        ``"R1006000"``, a bildvisning/IIIF URL, or a NAD reference code (see
        :mod:`ra_mcp_diplomatics_lib.identifiers`).

        Returns the record dict, or None if the reference is unparseable or names
        no record.
        """
        parsed = parse_mpo_id(mpo_id)
        if parsed is None:
            return None
        table = self._db.open_table(MPO_TABLE)
        rows = table.search().where(equals("id", parsed)).limit(1).to_list()
        return rows[0] if rows else None

    def get_mpo_by_ids(self, mpo_ids: Sequence[int | str]) -> list[dict]:
        """Look up several MPO records by fragment id in one query.

        Accepts the same written forms as :meth:`get_mpo_by_id`. Records are
        returned in the order the ids were requested (not table order), and ids
        that name no record are simply absent — the caller compares against its
        own input to report which ones were missing.
        """
        wanted = [parsed for raw in mpo_ids if (parsed := parse_mpo_id(raw)) is not None]
        if not wanted:
            return []

        table = self._db.open_table(MPO_TABLE)
        # One IN-predicate rather than a query per id: the BTree on `id` makes each
        # a point lookup, but the per-query overhead is what dominates a batch.
        predicate = any_of(*(equals("id", mpo_id) for mpo_id in wanted))
        rows = table.search().where(predicate).limit(len(wanted)).to_list()

        by_id = {row["id"]: row for row in rows}
        return [by_id[mpo_id] for mpo_id in wanted if mpo_id in by_id]
