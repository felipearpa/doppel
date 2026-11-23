# Adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/report.py (0BSD).
"""The text report: one group per function that has a copy."""

from __future__ import annotations

from doppel.model import Duplicate, Span


def _location(span: Span, name: str | None, gap: str) -> str:
    """The location, then the name when the function has one."""

    location = f"{span.file}:{span.start_line}-{span.end_line}"
    return location if name is None else f"{location}{gap}{name}"


def _sides(
    duplicate: Duplicate, focus: frozenset[Span] | None, rank: dict[Span, int]
) -> list[tuple[Span, Span]]:
    """The (heading, copy) placements of one pair.

    With no focus, a pair is listed once, under its side earlier in scan order.
    With a focus, it is listed under each side in it, so each touched function's
    group is complete.
    """

    both = [(duplicate.left, duplicate.right), (duplicate.right, duplicate.left)]
    if focus is None:
        return [min(both, key=lambda sides: rank[sides[0]])]
    return [(heading, copy) for heading, copy in both if heading in focus]


def format_text(duplicates: list[Duplicate], scanned: list[Span], focus: frozenset[Span] | None) -> str:
    """Groups in scan order, the order of `scanned`, each heading's copies closest
    first and, at one score, in scan order."""

    rank = {span: index for index, span in enumerate(scanned)}
    names = {}
    groups: dict[Span, list[tuple[float, Span]]] = {}
    for duplicate in duplicates:
        names[duplicate.left] = duplicate.left_name
        names[duplicate.right] = duplicate.right_name
        for heading, copy in _sides(duplicate, focus, rank):
            groups.setdefault(heading, []).append((duplicate.score, copy))
    if not groups:
        return "No duplicate candidates found.\n"
    blocks = []
    for heading in sorted(groups, key=rank.__getitem__):
        copies = sorted(groups[heading], key=lambda item: (-item[0], rank[item[1]]))
        lines = [
            _location(heading, names[heading], " "),
            *(f"  {score:.2f}  {_location(copy, names[copy], '  ')}" for score, copy in copies),
        ]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"
