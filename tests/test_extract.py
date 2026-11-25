from dataclasses import replace
from pathlib import Path

from doppel.extract import entries_in_source
from doppel.languages.kotlin import SPEC as KOTLIN
from doppel.shape import jaccard
from doppel.treesitter import child_of_type

# A Kotlin function given as two pieces, its name and its body: its parameters,
# return type and annotations are outside both.
STAND_IN_SPEC = replace(
    KOTLIN,
    name="standin",
    candidates=lambda root: [
        (child_of_type(node, "simple_identifier"), child_of_type(node, "function_body"))
        for node in KOTLIN.candidates(root)
    ],
    named_by=lambda pieces: pieces[0],
)


def entries(source: str):
    found, _has_error = entries_in_source(STAND_IN_SPEC, source, Path("a.kt"), "a.kt")
    return found


def score(left: str, right: str) -> float:
    [first] = entries(left)
    [second] = entries(right)
    return jaccard(first.fingerprints, second.fingerprints)


ALPHA = """\
@Deprecated("old")
fun alpha(xs: List<Int>): List<Int> {
    val ys = xs.filter(odd)
    return map(ys)
}
"""


def test_given_a_function_given_as_two_pieces_when_extracted_then_its_lines_run_from_the_first_piece_to_the_last():
    [entry] = entries(ALPHA)
    assert (entry.name, entry.start_line, entry.end_line) == ("alpha", 2, 5)


def test_given_two_pieces_when_scored_then_only_what_they_hold_counts():
    other_signature = """\
fun beta(items: Set<String>, extra: Int): Int {
    val kept = items.filter(even)
    return map(kept)
}
"""
    other_call = """\
fun beta(xs: List<Int>): List<Int> {
    val ys = xs.filter(odd)
    return fold(ys)
}
"""
    assert score(ALPHA, other_signature) == 1.0
    assert score(ALPHA, other_call) < 1.0


def test_given_pieces_in_another_order_when_scored_then_below_one():
    swapped = replace(STAND_IN_SPEC, candidates=lambda root: [tuple(reversed(pieces)) for pieces in STAND_IN_SPEC.candidates(root)])
    [entry] = entries(ALPHA)
    [other], _has_error = entries_in_source(swapped, ALPHA, Path("a.kt"), "a.kt")
    assert jaccard(entry.fingerprints, other.fingerprints) < 1.0


TRAILED = """\
fun alpha(xs: List<Int>): List<Int> {
    return map(xs)
}

// trailing
/* and a block
   on two lines */
"""


def test_given_a_node_ending_in_comments_when_extracted_then_its_lines_end_at_its_last_line_that_is_not_a_comment():
    whole_file = replace(KOTLIN, name="standin", candidates=lambda root: [root], named_by=lambda root: None)
    [entry], _has_error = entries_in_source(whole_file, TRAILED, Path("a.kt"), "a.kt")
    assert (entry.start_line, entry.end_line) == (1, 3)


def test_given_a_last_piece_that_is_a_comment_when_extracted_then_its_lines_end_at_the_piece_before():
    with_comment = replace(
        STAND_IN_SPEC,
        candidates=lambda root: [(*pieces, child_of_type(root, "line_comment")) for pieces in STAND_IN_SPEC.candidates(root)],
    )
    [entry], _has_error = entries_in_source(with_comment, TRAILED, Path("a.kt"), "a.kt")
    assert (entry.name, entry.start_line, entry.end_line) == ("alpha", 1, 3)


ZIPPED = """\
fun alpha(xs: List<Int>): List<Int> {
    return RIGHT
}
"""


def test_given_a_call_naming_two_children_in_call_position_when_scored_then_each_name_counts():
    # `xs zip ys` names its callee in the middle; the stand-in also keeps the right operand.
    both = replace(STAND_IN_SPEC, calls={**KOTLIN.calls, "infix_expression": lambda node: tuple(node.named_children[1:])})

    def scored(spec, left: str, right: str) -> float:
        [first], _has_error = entries_in_source(spec, ZIPPED.replace("RIGHT", left), Path("a.kt"), "a.kt")
        [second], _has_error = entries_in_source(spec, ZIPPED.replace("RIGHT", right), Path("b.kt"), "b.kt")
        return jaccard(first.fingerprints, second.fingerprints)

    assert scored(STAND_IN_SPEC, "xs zip ys", "xs zip zs") == 1.0
    assert scored(both, "xs zip ys", "xs zip zs") < 1.0
    assert scored(both, "xs zip ys", "xs with ys") < 1.0
    assert scored(both, "xs zip ys", "items zip ys") == 1.0
