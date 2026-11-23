# Adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/treesitter.py (0BSD).
"""Shared tree-sitter helpers."""

from functools import lru_cache


@lru_cache(maxsize=None)
def parser_for(language: str):
    from tree_sitter_language_pack import download, get_parser

    download([language])
    return get_parser(language)


def parse(source: str, language: str):
    data = source.encode("utf-8")
    tree = parser_for(language).parse(data)
    return data, tree


def node_text(data: bytes, node) -> str:
    return data[node.start_byte : node.end_byte].decode("utf-8")


def start_line(node) -> int:
    return node.start_point[0] + 1


def end_line(node) -> int:
    row, col = node.end_point
    if col == 0:
        return max(start_line(node), row)
    return row + 1


def descendants(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def child_of_type(node, *types: str):
    for child in node.children:
        if child.type in types:
            return child
    return None


def first_named(node):
    return node.named_children[0] if node.named_children else None


def last_named(node):
    return node.named_children[-1] if node.named_children else None


def middle_named(node):
    """The operator of `a op b`: the middle of exactly three named children."""

    return node.named_children[1] if len(node.named_children) == 3 else None
