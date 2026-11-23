# Copied from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/model.py (0BSD).
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """Where one function sits in a source file."""

    file: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Duplicate:
    """One pair of functions whose normalized structure is similar enough to report.

    A name travels beside its side's location and is not part of its identity.
    """

    score: float
    language: str
    left: Span
    left_name: str | None
    right: Span
    right_name: str | None


@dataclass(frozen=True)
class Entry:
    """A normalized function ready to compare. Functions are only compared within one language."""

    language: str
    file: str
    start_line: int
    end_line: int
    name: str | None
    nodes: int
    fingerprints: frozenset[str]
