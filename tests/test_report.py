from doppel.model import Duplicate, Span
from doppel.report import format_text

EARLIER = Span("a.kt", 1, 4)
LATER = Span("b.kt", 1, 4)


def test_given_a_pair_whose_right_side_comes_first_in_scan_order_when_reported_with_no_focus_then_the_right_side_is_the_heading():
    out = format_text(
        [Duplicate(1.0, "kotlin", left=LATER, left_name="sums", right=EARLIER, right_name="totals")],
        [EARLIER, LATER],
        None,
    )

    assert out == "a.kt:1-4 totals\n  1.00  b.kt:1-4  sums\n"


def test_given_functions_with_no_name_when_reported_then_their_lines_end_after_the_location():
    out = format_text(
        [Duplicate(0.95, "swift", left=EARLIER, left_name=None, right=LATER, right_name=None)],
        [EARLIER, LATER],
        frozenset({EARLIER, LATER}),
    )

    assert out == "a.kt:1-4\n  0.95  b.kt:1-4\n\nb.kt:1-4\n  0.95  a.kt:1-4\n"
