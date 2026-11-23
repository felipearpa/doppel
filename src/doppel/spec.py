# `_inside` copied from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/extract.py (0BSD).
"""What a language spec answers. The engine reads these fields and names no language."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from doppel.treesitter import child_of_type, descendants


def _inside(node, types: frozenset[str]) -> bool:
    current = node.parent
    while current is not None:
        if current.type in types:
            return True
        current = current.parent
    return False


@dataclass(frozen=True)
class CandidateRule:
    """A candidate is a node of one of `types` that has a `body` child and sits
    inside none of the `enclosing` types.
    """

    types: frozenset[str]
    body: str
    enclosing: frozenset[str]

    def __call__(self, root) -> list:
        return [
            node
            for node in descendants(root)
            if node.type in self.types
            and child_of_type(node, self.body) is not None
            and not _inside(node, self.enclosing)
        ]


@dataclass(frozen=True)
class LanguageSpec:
    """Everything doppel knows about one language.

    `grammar` names the tree-sitter grammar that parses a given file.
    `skips` says whether a file or folder under the walked folder is left
    out: test code, build output, dependencies. Its path starts with the
    walked folder's own name, then the path below it (`src/test/A.kt` when
    `src` is walked). That first part is context only, never a reason to
    skip: a spec may read it as a parent such as `src`, and applies its
    folder and file-name rules to the parts after it.
    `candidates` returns the nodes to compare under a parsed root: a
    `CandidateRule`, or a small function when data is not enough.
    `named_by` returns the child of a candidate that holds its name, or None
    when it has none; the name is printed as the source writes it.

    The rest give node types their role in normalization. `calls` maps each
    call node type to a function returning the child that names the callee.
    `members` maps each member-access node type to a function returning the
    child that holds the member's name, which is kept when it is called.
    `kept_tokens` are the unnamed tokens kept as structure: operators, and
    keywords that change meaning where one node type covers several of them.
    `interpolations` are the child node types that make a literal structure
    instead of a generic marker: a string with an interpolated part.
    """

    name: str
    extensions: frozenset[str]
    grammar: Callable[[Path], str]
    skips: Callable[[PurePosixPath], bool]
    candidates: Callable[[object], list]
    named_by: Callable[[object], object | None]
    comments: frozenset[str]
    identifiers: frozenset[str]
    literals: frozenset[str]
    parenthesized: frozenset[str]
    calls: Mapping[str, Callable[[object], object | None]]
    members: Mapping[str, Callable[[object], object | None]]
    kept_tokens: frozenset[str]
    interpolations: frozenset[str]
