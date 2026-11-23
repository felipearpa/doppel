"""Everything doppel knows about Kotlin.

Node names are those of the fwcd/tree-sitter-kotlin grammar shipped in
tree-sitter-language-pack 1.25.2.
"""

from pathlib import PurePosixPath

from doppel.spec import CandidateRule, LanguageSpec
from doppel.treesitter import child_of_type, first_named, last_named, middle_named

_FUNCTIONS = CandidateRule(
    types=frozenset({"function_declaration"}),
    body="function_body",
    enclosing=frozenset(
        {
            "function_declaration",
            "anonymous_function",
            "lambda_literal",
            "getter",
            "setter",
            "anonymous_initializer",
            "secondary_constructor",
        }
    ),
)


def _block_bodied(root) -> list:
    """`fun x() { … }`, not `fun x() = …`.

    The grammar wraps both bodies in `function_body`; only the first token
    tells them apart.
    """

    return [
        node
        for node in _FUNCTIONS(root)
        if child_of_type(child_of_type(node, "function_body"), "{") is not None
    ]


_BUILD_FOLDERS = frozenset({"build", ".gradle"})
_TEST_FILE_ENDINGS = ("Test.kt", "Tests.kt", "Spec.kt")


def _skips(path: PurePosixPath) -> bool:
    """Build output, test source sets and test files.

    A test source set is a folder right under `src` whose name contains
    "test": `test`, `androidTest`, `commonTest`, `testFixtures`.
    """

    parts = path.parts
    below = parts[1:]
    # Build output sits beside `src`; a package called `build` inside it is code.
    # The first part, the walked folder's name, counts as a `src` parent, never as a `build`.
    above_src = parts[1 : parts.index("src")] if "src" in parts else below
    if _BUILD_FOLDERS.intersection(above_src) or (below and below[-1].endswith(_TEST_FILE_ENDINGS)):
        return True
    return any(
        parent == "src" and "test" in child.lower() and not child.endswith(".kt")
        for parent, child in zip(parts, parts[1:])
    )


SPEC = LanguageSpec(
    name="kotlin",
    extensions=frozenset({".kt"}),
    grammar=lambda path: "kotlin",
    skips=_skips,
    candidates=_block_bodied,
    # The name is the first direct identifier: the receiver of `fun String.total()`
    # and the type parameters of `fun <T> f()` are nodes of their own.
    named_by=lambda node: child_of_type(node, "simple_identifier"),
    comments=frozenset({"line_comment", "multiline_comment"}),
    identifiers=frozenset(
        {"simple_identifier", "type_identifier", "interpolated_identifier", "label"}
    ),
    literals=frozenset(
        {
            "string_literal",
            "character_literal",
            "integer_literal",
            "hex_literal",
            "bin_literal",
            "real_literal",
            "long_literal",
            "unsigned_literal",
            "boolean_literal",
            "null_literal",
        }
    ),
    parenthesized=frozenset({"parenthesized_expression"}),
    # `foo(x)`, `a.b.foo(x)`, `foo<T>(x)`, `foo { }`: the callee comes first.
    # `a shl b`, `0 until n`: the callee sits between the operands.
    calls={"call_expression": first_named, "infix_expression": middle_named},
    # `a.b` is `navigation_expression` → `a`, `navigation_suffix` → `.`, `b`.
    members={"navigation_expression": last_named, "navigation_suffix": last_named},
    # `return x` and `throw x` are both `jump_expression`; `!in` and `!is` are
    # the `!` token followed by `in` or `is`. Modifiers, `val` and `var` are
    # not kept.
    kept_tokens=frozenset(
        {
            "return",
            "throw",
            "break",
            "continue",
            # `break@outer`: a labeled jump is one token, followed by its label.
            "return@",
            "break@",
            "continue@",
            "!!",
            "?.",
            "::",
            "as",
            "as?",
            "in",
            "is",
            "!",
            "..",
            "..<",
            "?:",
            "&&",
            "||",
            "+",
            "-",
            "*",
            "/",
            "%",
            "++",
            "--",
            "==",
            "!=",
            "===",
            "!==",
            # Also the brackets of type arguments, as in `List<Int>`.
            "<",
            ">",
            "<=",
            ">=",
            "=",
            "+=",
            "-=",
            "*=",
            "/=",
            "%=",
        }
    ),
    # `"${f(x)}"` and `"$x"`: the text around them stays out of the structure.
    interpolations=frozenset({"interpolated_expression", "interpolated_identifier"}),
)
