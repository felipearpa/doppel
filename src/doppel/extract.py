# Adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/extract.py (0BSD).
"""Turn each candidate the spec picks into an entry ready to compare."""

from __future__ import annotations

from pathlib import Path

from doppel.astnorm import normalize
from doppel.model import Entry
from doppel.shape import fingerprints, node_count
from doppel.spec import LanguageSpec
from doppel.treesitter import end_line, node_text, parse, start_line


def entries_in_source(
    spec: LanguageSpec, source: str, path: Path, file: str
) -> tuple[list[Entry], bool]:
    """The entries in `source`, and whether the grammar could not fully parse it."""

    data, tree = parse(source, spec.grammar(path))
    entries = []
    for node in spec.candidates(tree.root_node):
        normalized = normalize(node, data, spec)
        name = spec.named_by(node)
        entries.append(
            Entry(
                language=spec.name,
                file=file,
                start_line=start_line(node),
                end_line=end_line(node),
                name=None if name is None else node_text(data, name),
                nodes=node_count(normalized),
                fingerprints=fingerprints(normalized),
            )
        )
    return entries, tree.root_node.has_error
