# Reworked from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/astnorm.py (0BSD).
"""Normalize a tree-sitter tree, reading each node type's role from the spec.

The name in call position stays: `filter` in `filter(xs)`, the `foo` in
`a.b.foo(x)`. Local names, type names, a member that is only read, and
literals become generic markers. Comments and unnamed tokens are dropped,
except the operators and keywords the spec keeps. A literal with an
interpolated part keeps its structure, so a call inside it counts.
Parentheses around one expression are unwrapped. Two functions that call the
same operations in the same shape therefore share a fingerprint set even when
their locals differ.
"""

from __future__ import annotations

from doppel.shape import K
from doppel.spec import LanguageSpec
from doppel.treesitter import node_text

_PENDING = object()


def _leaf(node, head: bool, data: bytes, spec: LanguageSpec):
    if node.type in spec.comments:
        return None
    if not node.is_named:
        if node.type in spec.kept_tokens:
            return [K("symbol"), node.type]
        return None
    if node.type in spec.identifiers:
        if head:
            return [K("symbol"), node_text(data, node)]
        return K("symbol")
    if node.type in spec.literals and not any(
        child.type in spec.interpolations for child in node.children
    ):
        return K("literal")
    return _PENDING


def _callee_ids(node, head: bool, spec: LanguageSpec) -> set[int]:
    if node.type in spec.calls:
        target = spec.calls[node.type](node)
    elif head and node.type in spec.members:
        target = spec.members[node.type](node)
    elif head and node.type in spec.parenthesized:
        return {child.id for child in node.children}
    else:
        return set()
    return set() if target is None else {target.id}


def _assemble(node, spec: LanguageSpec, done: dict):
    children = [done[child.id] for child in node.children if done[child.id] is not None]
    if node.type in spec.parenthesized and len(children) == 1:
        return children[0]
    return [K(node.type), *children]


def normalize(node, data: bytes, spec: LanguageSpec):
    """Normalized tree for `node`, or None when the node is dropped."""

    # Post-order. A 1,200-deep expression must not raise RecursionError.
    # Nodes are keyed by `Node.id`: tree-sitter hands out a new Python object
    # for the same node, so `id()` would not match.
    done: dict = {}
    stack = [(node, False, False)]
    while stack:
        current, head, expanded = stack.pop()
        if expanded:
            done[current.id] = _assemble(current, spec, done)
            continue
        leaf = _leaf(current, head, data, spec)
        if leaf is not _PENDING:
            done[current.id] = leaf
            continue
        stack.append((current, head, True))
        callees = _callee_ids(current, head, spec)
        for child in reversed(current.children):
            stack.append((child, child.id in callees, False))
    return done[node.id]
