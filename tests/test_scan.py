from doppel.model import Entry
from doppel.scan import find_duplicates, span_of


def entry(file: str, start: int, end: int, names: set[str]) -> Entry:
    return Entry("kotlin", file, start, end, "f", 20, frozenset(names))


def test_given_two_entries_with_the_same_span_when_paired_then_they_are_not_a_pair():
    assert find_duplicates([entry("a.kt", 1, 4, {"q"}), entry("a.kt", 1, 4, {"q"})], 0.0) == []
    assert len(find_duplicates([entry("a.kt", 1, 4, {"q"}), entry("b.kt", 1, 4, {"q"})], 0.5)) == 1
    assert len(find_duplicates([entry("a.kt", 1, 5, {"q"}), entry("a.kt", 3, 5, {"q"})], 0.5)) == 1
    assert len(find_duplicates([entry("a.kt", 1, 4, {"q"}), entry("a.kt", 1, 8, {"q"})], 0.5)) == 1


def test_given_a_score_equal_to_the_threshold_when_paired_then_the_pair_is_kept():
    left = entry("a.kt", 1, 4, {"x", "y"})
    right = entry("b.kt", 1, 4, {"x", "z"})
    assert len(find_duplicates([left, right], 1 / 3)) == 1
    assert find_duplicates([left, right], 1 / 3 + 0.01) == []


def test_given_pairs_with_different_scores_when_paired_then_the_higher_score_is_listed_first():
    partial = [entry("a.kt", 1, 4, {"x", "y"}), entry("b.kt", 10, 14, {"x", "z"})]
    exact = [entry("c.kt", 1, 4, {"only"}), entry("d.kt", 1, 4, {"only"})]
    found = find_duplicates(partial + exact, 0.3)
    assert [item.score for item in found] == [1.0, 1 / 3]


def test_given_a_focus_when_paired_then_a_pair_with_neither_side_in_it_is_not_listed():
    edited = entry("a.kt", 1, 4, {"q"})
    copy = entry("b.kt", 1, 4, {"q"})
    other = entry("c.kt", 1, 4, {"q"})
    found = find_duplicates([edited, copy, other], 0.5, frozenset({span_of(edited)}))
    assert [(item.left.file, item.right.file) for item in found] == [("a.kt", "b.kt"), ("a.kt", "c.kt")]


def test_given_a_focus_on_one_function_when_paired_then_its_neighbour_in_the_same_file_is_not_in_it():
    edited = entry("a.kt", 1, 4, {"q"})
    neighbour = entry("a.kt", 6, 9, {"r"})
    found = find_duplicates(
        [edited, neighbour, entry("b.kt", 1, 4, {"q"}), entry("c.kt", 1, 4, {"r"})], 0.5, frozenset({span_of(edited)})
    )
    assert [(item.left, item.right) for item in found] == [(span_of(edited), span_of(entry("b.kt", 1, 4, set())))]


def test_given_an_empty_focus_when_paired_then_nothing_is_listed():
    assert find_duplicates([entry("a.kt", 1, 4, {"q"}), entry("b.kt", 1, 4, {"q"})], 0.5, frozenset()) == []
