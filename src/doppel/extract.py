# Adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/extract.py (0BSD).
"""Turn each candidate the spec picks into an entry ready to compare."""

from __future__ import annotations

from pathlib import Path

from doppel.astnorm import normalize
from doppel.model import Entry
from doppel.shape import K, fingerprints, node_count
from doppel.spec import LanguageSpec
from doppel.treesitter import end_line, node_text, parse, start_line


def _normalized(pieces: tuple, data: bytes, spec: LanguageSpec):
    """Pieces are joined under one head no node type has, so a function given
    as one node keeps the fingerprints it has alone."""

    normalized = [normalize(piece, data, spec) for piece in pieces]
    return [K("doppel/pieces"), *(piece for piece in normalized if piece is not None)]


def _last_line(pieces, comments: frozenset[str]) -> int:
    """The last line of the last token that is not in a comment, at any depth:
    a grammar may end a node, or give as its last piece, the comment after it.
    """

    stack = list(pieces)
    while stack:
        node = stack.pop()
        if node.type in comments:
            continue
        if not node.child_count:
            return end_line(node)
        stack.extend(node.children)
    return end_line(pieces[-1])


def entries_in_source(
    spec: LanguageSpec, source: str, path: Path, file: str
) -> tuple[list[Entry], bool]:
    """The entries in `source`, and whether the grammar could not fully parse it."""

    data, tree = parse(source, spec.grammar(path))
    entries = []
    for candidate in spec.candidates(tree.root_node):
        if isinstance(candidate, tuple):
            pieces, normalized = candidate, _normalized(candidate, data, spec)
        else:
            pieces, normalized = (candidate,), normalize(candidate, data, spec)
        name = spec.named_by(candidate)
        entries.append(
            Entry(
                language=spec.name,
                file=file,
                start_line=start_line(pieces[0]),
                end_line=_last_line(pieces, spec.comments),
                name=None if name is None else node_text(data, name),
                nodes=node_count(normalized),
                fingerprints=fingerprints(normalized),
            )
        )
    return entries, tree.root_node.has_error
