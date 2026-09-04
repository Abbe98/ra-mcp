"""Parsing and rendering of MPO fragment identifiers.

An MPO fragment is identified by a single integer — the ``signatur`` column of
the source CSV, stored as ``id`` — but that integer is written several ways in
the wild, and a user typing any of them means the same fragment:

===========================================  ==========================
Form                                         Example
===========================================  ==========================
Canonical signature (Riksarkivet's MPO db)   ``Fr 6000``
Bare fragment number                         ``6000``
Namespaced                                   ``MPO 6000``, ``MPO Fr 6000``
ARKIS image id (offset by 1,000,000)         ``R1006000``
Bildvisning / IIIF manifest URL              ``.../bildvisning/R1006000``
NAD reference code                           ``SE/RA/80001/Nr 5001-6000/6000``
===========================================  ==========================

:func:`parse_mpo_reference` accepts all of them and reports whether the input
carried an explicit marker (``Fr``, ``MPO``, an ``R1…`` id, a URL). That flag is
what lets a caller distinguish "the user unambiguously named fragment 6000" from
"the user typed ``6000``, which *might* be a fragment number and might be a year
or a shelf mark they want full-text searched".
"""

from __future__ import annotations

import re
from typing import NamedTuple


__all__ = [
    "MAX_MPO_ID",
    "MPOReference",
    "format_mpo_signature",
    "mpo_bildvisning_url",
    "mpo_image_id",
    "parse_mpo_id",
    "parse_mpo_ids",
    "parse_mpo_reference",
]


# The MPO corpus holds ~23,000 fragments; the published ids run into the 29,000s.
# The bound only rejects input that cannot be a fragment number at all (a year
# range, a phone number, an ARKIS id parsed as a bare integer) — it is deliberately
# loose so the dataset can grow without this module going stale.
MAX_MPO_ID = 99_999

# Riksarkivet's image service names an MPO fragment ``R{1_000_000 + id}``:
# fragment 6000 is ``R1006000`` in both the bildvisning URL and the IIIF manifest.
MPO_IMAGE_ID_OFFSET = 1_000_000

MPO_BILDVISNING_TEMPLATE = "https://sok.riksarkivet.se/bildvisning/{image_id}"

# "Fr 6000" — how Riksarkivet's MPO database titles each record, and how the
# fragments are cited in the codicological literature.
MPO_SIGNATURE_PREFIX = "Fr"

# An ARKIS id anywhere in the input (bare, or inside a bildvisning/IIIF URL).
_IMAGE_ID_RE = re.compile(r"\bR(\d{7,8})\b", re.IGNORECASE)

# A fragment number, optionally prefixed by "MPO" and/or "Fr"/"Fragment", with an
# optional separator (space, colon, hash, dot, hyphen) between prefix and number.
_SIGNATURE_RE = re.compile(
    r"""
    ^
    (?:(?P<mpo>mpo)\s*[:#.\-]?\s*)?          # optional "MPO" namespace
    (?:(?P<fr>fr|fragment)\s*[:#.\-]?\s*)?   # optional "Fr" / "Fragment" marker
    \#?                                       # optional bare "#"
    (?P<number>\d{1,6})
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)


class MPOReference(NamedTuple):
    """A parsed MPO fragment reference.

    Attributes:
        id: The fragment number (the ``signatur``/``id`` column).
        explicit: True when the input named MPO unambiguously — an ``Fr``/``MPO``
            marker, an ``R1…`` ARKIS id, or a reference code. False for a bare
            number, which a caller may want to treat as *both* a candidate id and
            a full-text search term.
    """

    id: int
    explicit: bool


def _in_range(number: int) -> bool:
    return 1 <= number <= MAX_MPO_ID


def parse_mpo_reference(value: str | int | None) -> MPOReference | None:
    """Parse any written form of an MPO fragment id.

    Returns None when ``value`` is not a fragment reference at all (free-text
    search terms, out-of-range numbers, empty input).

    >>> parse_mpo_reference("Fr 6000")
    MPOReference(id=6000, explicit=True)
    >>> parse_mpo_reference("6000")
    MPOReference(id=6000, explicit=False)
    >>> parse_mpo_reference("https://sok.riksarkivet.se/bildvisning/R1006000")
    MPOReference(id=6000, explicit=True)
    >>> parse_mpo_reference("Missale")  # returns None
    """
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass; never a fragment id
        return None
    if isinstance(value, int):
        return MPOReference(value, True) if _in_range(value) else None

    text = value.strip()
    if not text:
        return None

    # ARKIS image id, bare or embedded in a bildvisning / IIIF manifest URL.
    if match := _IMAGE_ID_RE.search(text):
        number = int(match.group(1)) - MPO_IMAGE_ID_OFFSET
        return MPOReference(number, True) if _in_range(number) else None

    # NAD reference code (SE/RA/80001/Nr 5001-6000/6000): the fragment number is
    # the final path segment; the preceding "Nr 5001-6000" is just the shelf block.
    if "/" in text:
        tail = text.rsplit("/", 1)[-1].strip()
        if tail.isdigit():
            number = int(tail)
            return MPOReference(number, True) if _in_range(number) else None
        return None

    if match := _SIGNATURE_RE.match(text):
        number = int(match.group("number"))
        if not _in_range(number):
            return None
        explicit = bool(match.group("mpo") or match.group("fr"))
        return MPOReference(number, explicit)

    return None


def parse_mpo_id(value: str | int | None) -> int | None:
    """Return the fragment number named by ``value``, or None if it names none.

    Convenience wrapper around :func:`parse_mpo_reference` for callers that do not
    care whether the reference was explicit.
    """
    reference = parse_mpo_reference(value)
    return reference.id if reference else None


def parse_mpo_ids(value: str | int | None) -> tuple[list[int], list[str]]:
    """Parse a list of fragment references separated by commas, semicolons or whitespace.

    Handles the shapes a user actually types — ``"Fr 6000, Fr 6001"``,
    ``"6000 6001"``, ``"6000; 6001"`` — including the space *inside* ``Fr 6000``,
    which is why whitespace alone cannot be used as the separator.

    Returns:
        ``(ids, unparsed)``: the fragment numbers in input order (duplicates
        removed) and the tokens that could not be parsed, so the caller can report
        exactly which part of the input it did not understand.
    """
    if value is None:
        return [], []
    if isinstance(value, int) and not isinstance(value, bool):
        parsed = parse_mpo_id(value)
        return ([parsed], []) if parsed is not None else ([], [str(value)])

    text = str(value).strip()
    if not text:
        return [], []

    # Split on explicit separators first; only fall back to whitespace splitting
    # for a token that is not itself a valid reference, so "Fr 6000" survives.
    tokens = [t.strip() for t in re.split(r"[,;]", text) if t.strip()]

    ids: list[int] = []
    unparsed: list[str] = []
    seen: set[int] = set()

    for token in tokens:
        for part in _split_token(token):
            parsed = parse_mpo_id(part)
            if parsed is None:
                unparsed.append(part)
            elif parsed not in seen:
                seen.add(parsed)
                ids.append(parsed)

    return ids, unparsed


def _split_token(token: str) -> list[str]:
    """Split a comma-free token into individual references.

    ``"Fr 6000"`` is one reference, but ``"6000 6001"`` and ``"Fr 6000 Fr 6001"``
    are two — so the token is only split on whitespace when it does not already
    parse as a single reference.
    """
    if parse_mpo_reference(token) is not None:
        return [token]
    parts = token.split()
    if len(parts) < 2:
        return [token]
    # Re-join an "Fr"/"MPO" marker with the number that follows it.
    merged: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part.lower().rstrip(".:#-") in {"fr", "fragment", "mpo"} and index + 1 < len(parts):
            merged.append(f"{part} {parts[index + 1]}")
            index += 2
        else:
            merged.append(part)
            index += 1
    return merged


def format_mpo_signature(mpo_id: int) -> str:
    """Render a fragment number as its canonical signature: ``6000`` → ``"Fr 6000"``."""
    return f"{MPO_SIGNATURE_PREFIX} {mpo_id}"


def mpo_image_id(mpo_id: int) -> str:
    """Render the ARKIS image id for a fragment: ``6000`` → ``"R1006000"``."""
    return f"R{MPO_IMAGE_ID_OFFSET + mpo_id}"


def mpo_bildvisning_url(mpo_id: int) -> str:
    """Render the bildvisning (image viewer) URL for a fragment."""
    return MPO_BILDVISNING_TEMPLATE.format(image_id=mpo_image_id(mpo_id))
