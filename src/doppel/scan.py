# Adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/scan.py (0BSD).
"""Read source files and pair the functions that clear the similarity threshold."""

from __future__ import annotations

from pathlib import Path

from doppel.discover import spec_of
from doppel.extract import entries_in_source
from doppel.model import Duplicate, Entry, Span
from doppel.shape import jaccard
from doppel.treesitter import ParserUnavailable


class LanguageUnavailable(Exception):
    """A language whose parser cannot be loaded, named by its spec, and why."""

    def __init__(self, language: str, reason: str):
        super().__init__(language, reason)
        self.language = language
        self.reason = reason


def display_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _keep(entry: Entry, min_lines: int, min_nodes: int) -> bool:
    lines = entry.end_line - entry.start_line + 1
    return lines >= min_lines and entry.nodes >= min_nodes


def scan_files(
    files: list[Path], root: Path, min_lines: int, min_nodes: int
) -> tuple[list[Entry], list[str], list[str]]:
    """The entries to compare, the files the grammar could not fully parse, and
    the files that could not be read.

    A file with parse errors is compared as parsed; an unreadable one is left out.
    Raises LanguageUnavailable when a file's parser cannot be loaded.
    """

    entries: list[Entry] = []
    broken: list[str] = []
    unreadable: list[str] = []
    for path in files:
        spec = spec_of(path)
        if spec is None:
            continue
        file = display_path(path, root)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            unreadable.append(file)
            continue
        try:
            found, has_error = entries_in_source(spec, source, path, file)
        except ParserUnavailable as exc:
            raise LanguageUnavailable(spec.name, str(exc)) from exc
        if has_error:
            broken.append(file)
        entries.extend(entry for entry in found if _keep(entry, min_lines, min_nodes))
    return entries, broken, unreadable


def span_of(entry: Entry) -> Span:
    return Span(entry.file, entry.start_line, entry.end_line)


def _duplicate_key(item: Duplicate):
    return (
        -item.score,
        item.language,
        item.left.file,
        item.left.start_line,
        item.right.file,
        item.right.start_line,
    )


def find_duplicates(
    entries: list[Entry], threshold: float, focus: frozenset[Span] | None = None
) -> list[Duplicate]:
    """Pair functions of the same language. Each unordered pair is reported once.

    With `focus`, a set of functions, only pairs with at least one side in it are compared.
    """

    by_language: dict[str, list[tuple[Entry, Span]]] = {}
    for entry in entries:
        by_language.setdefault(entry.language, []).append((entry, span_of(entry)))

    found: list[Duplicate] = []
    for language, group in by_language.items():
        for index, (left, left_span) in enumerate(group):
            for right, right_span in group[index + 1 :]:
                if left_span == right_span:
                    continue
                if focus is not None and left_span not in focus and right_span not in focus:
                    continue
                score = jaccard(left.fingerprints, right.fingerprints)
                if score < threshold:
                    continue
                found.append(
                    Duplicate(
                        score=score,
                        language=language,
                        left=left_span,
                        left_name=left.name,
                        right=right_span,
                        right_name=right.name,
                    )
                )
    found.sort(key=_duplicate_key)
    return found
