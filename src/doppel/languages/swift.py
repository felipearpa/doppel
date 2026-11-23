"""Everything doppel knows about Swift.

Node names are those of the alex-pinkus/tree-sitter-swift grammar shipped in
tree-sitter-language-pack 1.25.2.
"""

from pathlib import PurePosixPath

from doppel.spec import CandidateRule, LanguageSpec
from doppel.treesitter import child_of_type, first_named, last_named, middle_named

# `init`, `deinit`, `subscript`, computed properties and observers are left
# out, so SwiftUI `body` code is not compared.
_FUNCTIONS = CandidateRule(
    types=frozenset({"function_declaration"}),
    body="function_body",
    enclosing=frozenset(
        {
            "function_declaration",
            "lambda_literal",
            "init_declaration",
            "deinit_declaration",
            "subscript_declaration",
            "computed_property",
            "willset_didset_block",
        }
    ),
)

# SwiftPM, Xcode, CocoaPods and Carthage output and checkouts.
_TOOL_FOLDERS = frozenset({".build", "DerivedData", "Pods", "Carthage"})


def _skips(path: PurePosixPath) -> bool:
    """At any depth. The first part is the walked folder's name: context only."""

    below = path.parts[1:]
    return bool(_TOOL_FOLDERS.intersection(below)) or any(
        part.endswith(("Tests", "Tests.swift")) for part in below
    )


def _callee(node):
    """None for a subscript: the grammar reads `xs[i]` as a call to `xs`, a value."""

    suffix = child_of_type(node, "call_suffix")
    arguments = None if suffix is None else child_of_type(suffix, "value_arguments")
    if arguments is not None and arguments.children and arguments.children[0].type == "[":
        return None
    return first_named(node)


def _type_name(node):
    names = [child for child in node.named_children if child.type == "type_identifier"]
    return names[-1] if names else None


SPEC = LanguageSpec(
    name="swift",
    extensions=frozenset({".swift"}),
    grammar=lambda path: "swift",
    skips=_skips,
    candidates=_FUNCTIONS,
    # The grammar's `name` field also finds operators (`==`, a custom `<=>`), but
    # the return type carries the same field name: only the first match is the
    # function's name.
    named_by=lambda node: node.child_by_field_name("name"),
    comments=frozenset({"comment", "multiline_comment"}),
    # `custom_operator`, so an operator's text is kept as a callee.
    identifiers=frozenset({"simple_identifier", "type_identifier", "custom_operator"}),
    literals=frozenset(
        {
            "line_string_literal",
            "multi_line_string_literal",
            "raw_string_literal",
            "regex_literal",
            "integer_literal",
            "hex_literal",
            "oct_literal",
            "bin_literal",
            "real_literal",
            "boolean_literal",
            "nil_literal",
        }
    ),
    # The grammar reads `(map)` as a one-element tuple.
    parenthesized=frozenset({"tuple_expression"}),
    calls={
        # `[Int]()` is a call to an `array_literal`; `Set<Int>()` a constructor.
        "call_expression": _callee,
        "constructor_expression": first_named,
        # The grammar reads `!=`, `<=`, `>=` as a `custom_operator` between the operands.
        "infix_expression": middle_named,
    },
    members={
        "navigation_expression": last_named,
        "navigation_suffix": last_named,
        # `.success(x)` is a `prefix_expression`.
        "prefix_expression": last_named,
        # `[String: Int]()` keeps only the key type.
        "user_type": _type_name,
        "array_literal": first_named,
        "dictionary_literal": first_named,
    },
    # `return`, `break` and `continue` share a node type; `throw` has its own.
    # `try?` and `try!` differ only by their `?` or `!` token.
    kept_tokens=frozenset(
        {
            "return",
            # Unlike `throws`, the grammar leaves `async` unnamed.
            "async",
            "break",
            "continue",
            "as",
            "as?",
            "as!",
            "?",
            "!",
            "&",
            "...",
            "..<",
            "+",
            "-",
            "*",
            "/",
            "%",
            "==",
            "===",
            # Also the brackets of type arguments, as in `Array<Int>`.
            "<",
            ">",
            "=",
            "+=",
            "-=",
            "*=",
            "/=",
            "%=",
        }
    ),
    # A raw string holds its interpolation one level down.
    interpolations=frozenset({"interpolated_expression", "raw_str_interpolation"}),
)
