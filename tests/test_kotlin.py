from pathlib import Path

from doppel.cli import run
from doppel.discover import iter_source_files, spec_of
from doppel.scan import find_duplicates, scan_files
from doppel.shape import jaccard
from doppel.treesitter import end_line, parse, start_line
from helpers import commit_all, entries_of, write_source


def candidate_spans(source: str) -> list[tuple[int, int]]:
    path = Path("a.kt")
    spec = spec_of(path)
    _data, tree = parse(source, spec.grammar(path))
    return [(start_line(node), end_line(node)) for node in spec.candidates(tree.root_node)]


def test_given_nested_expression_bodied_and_bodiless_functions_when_picked_then_only_outer_block_bodied_remain():
    source = """\
class Box {
    fun member(): Int {
        fun inner() {
            g()
        }
        val o = object : Runnable {
            override fun run() {
                h()
            }
        }
        return 1
    }
    fun short() = 1
    fun lambdaBody() = run {
        fun inExpression() {
        }
    }
    fun noBody()
}
val top = object : Runnable {
    override fun run() {
    }
}
val lam = {
    fun inLambda() {
    }
}
fun topLevel() {
}
"""
    assert candidate_spans(source) == [(2, 12), (21, 22), (28, 29)]


def score(left: str, right: str) -> float:
    entries = entries_of(left, "a.kt")
    entries += entries_of(right, "b.kt")
    assert len(entries) == 2
    return jaccard(entries[0].fingerprints, entries[1].fingerprints)


ALPHA = """\
fun alpha(xs: List<Int>): List<Int> {
    // keep the odd ones
    val ys = xs.filter(odd)
    return (map)(ys, 1)
}
"""


def test_given_other_names_literals_comments_and_parentheses_when_scored_then_one():
    beta = """\
fun beta(items: List<Long>): List<Long> {
    val kept = items.filter(even)
    return map(kept, "two")
}
"""
    assert score(ALPHA, beta) == 1.0


def test_given_another_member_or_function_called_when_scored_then_below_one():
    other_member = """\
fun beta(items: List<Int>): List<Int> {
    val kept = items.select(even)
    return map(kept, 2)
}
"""
    other_function = """\
fun beta(items: List<Int>): List<Int> {
    val kept = items.filter(even)
    return fold(kept, 2)
}
"""
    assert score(ALPHA, other_member) < 1.0
    assert score(ALPHA, other_function) < 1.0


def function(statement: str, name: str = "alpha") -> str:
    return f"fun {name}(a: Int, b: Int) {{\n    {statement}\n}}\n"


def test_given_another_infix_function_when_scored_then_below_one():
    assert score(function("a shl b"), function("a until b", "beta")) < 1.0
    assert score(function("a shl b"), function("c shl d", "beta")) == 1.0


def test_given_another_callee_in_each_call_shape_when_scored_then_below_one():
    assert score(function("foo { }"), function("bar { }", "beta")) < 1.0
    assert score(function("listOf<Int>(a)"), function("setOf<Int>(a)", "beta")) < 1.0
    assert score(function("a.b.foo(a)"), function("a.b.bar(a)", "beta")) < 1.0


def test_given_another_keyword_when_scored_then_below_one():
    assert score(function("return a"), function("throw a", "beta")) < 1.0
    assert score(function("val c = a as Long"), function("val c = a as? Long", "beta")) < 1.0
    assert score(function("val c = a in b"), function("val c = a !in b", "beta")) < 1.0
    break_outer = "outer@ for (c in a) { break@outer }"
    continue_outer = "outer@ for (c in a) { continue@outer }"
    assert score(function(break_outer), function(continue_outer, "beta")) < 1.0


def test_given_a_swapped_modifier_when_scored_then_one():
    assert score("private " + function("return a"), "public " + function("return b", "beta")) == 1.0


def test_given_another_call_in_a_template_when_scored_then_below_one():
    assert score(function('return "sum ${foo(a)}"'), function('return "sum ${bar(a)}"', "beta")) < 1.0


def test_given_other_plain_string_text_when_scored_then_one():
    assert score(function('return "left"'), function('return "right"', "beta")) == 1.0
    assert score(function('return "left ${foo(a)}"'), function('return "right ${foo(b)}"', "beta")) == 1.0


def pairs(root: Path, threshold: float = 0.99):
    files = sorted(path for path in root.rglob("*") if path.is_file())
    entries, _broken, _unreadable = scan_files(files, root, min_lines=1, min_nodes=1)
    return find_duplicates(entries, threshold)


LEFT = """\
fun alpha(xs: List<Int>): List<Int> {
    val ys = filter(xs, odd)
    return map(ys, inc)
}
"""


def test_given_an_extra_statement_when_paired_then_below_one(tmp_path):
    write_source(tmp_path, "a.kt", LEFT)
    write_source(
        tmp_path,
        "b.kt",
        """\
fun beta(items: List<Int>): List<Int> {
    val kept = filter(items, even)
    val extra = filter(kept, even)
    return map(extra, dec)
}
""",
    )
    found = pairs(tmp_path, threshold=0.5)
    assert len(found) == 1
    assert found[0].score < 1.0


def test_given_other_receivers_read_members_and_type_arguments_when_paired_then_one(tmp_path):
    write_source(
        tmp_path,
        "a.kt",
        """\
fun alpha(xs: List<Int>): Int {
    val ys = ArrayList<String>()
    ys.add(xs)
    return xs.total
}
""",
    )
    write_source(
        tmp_path,
        "b.kt",
        """\
fun beta(items: List<Int>): Int {
    val kept = ArrayList<Long>()
    kept.add(items)
    return items.count
}
""",
    )
    found = pairs(tmp_path)
    assert [(item.left.file, item.right.file, item.score) for item in found] == [("a.kt", "b.kt", 1.0)]


def test_given_a_constructor_call_when_normalized_then_its_type_is_kept():
    source = """\
fun alpha() {
    val ys = ArrayList<String>()
}
"""
    [entry] = entries_of(source, "a.kt")
    assert '"ArrayList"' in entry.fingerprints


def test_given_a_nested_function_when_paired_then_the_outer_functions_pair_scoring_one(tmp_path):
    write_source(
        tmp_path,
        "a.kt",
        """\
fun alpha(xs: List<Int>): List<Int> {
    fun inner(ys: List<Int>): List<Int> {
        return filter(ys, odd)
    }
    return inner(xs)
}
""",
    )
    write_source(
        tmp_path,
        "b.kt",
        """\
fun beta(items: List<Int>): List<Int> {
    fun inner(kept: List<Int>): List<Int> {
        return filter(kept, even)
    }
    return inner(items)
}
""",
    )
    found = pairs(tmp_path)
    assert len(found) == 1
    assert found[0].score == 1.0
    assert (found[0].left.start_line, found[0].left.end_line) == (1, 6)


def test_given_five_copies_when_paired_then_ten_pairs(tmp_path):
    for index in range(5):
        write_source(tmp_path, f"copy{index}.kt", LEFT)
    found = pairs(tmp_path)
    assert len(found) == 10
    assert all(item.score == 1.0 for item in found)


def test_given_each_function_shape_when_extracted_then_its_name_is_the_name_the_source_writes():
    source = """\
fun plain(a: Int) {
}
fun String.total(): Int {
}
fun <T> generic(x: T): T {
}
operator fun Money.plus(other: Money): Money {
}
fun `returns total when paid`() {
}
"""
    assert [entry.name for entry in entries_of(source, "a.kt")] == [
        "plain",
        "total",
        "generic",
        "plus",
        "`returns total when paid`",
    ]


def test_given_an_extension_function_and_a_backticked_copy_when_doppel_runs_then_their_lines_show_their_names(tmp_path, capsys, monkeypatch):
    body = """\
(orders: List<Order>): Map<String, Int> {
    val paid = orders.filter { it.status == "paid" }
    val grouped = paid.groupBy { it.customer }
    return grouped.mapValues { entry -> entry.value.sumOf { it.amount } }
}
"""
    write_source(tmp_path, "A.kt", "fun Ledger.total" + body)
    write_source(tmp_path, "B.kt", "fun Ledger.`returns total when paid`" + body)
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0
    assert capsys.readouterr().out == "A.kt:1-5 total\n  1.00  B.kt:1-5  `returns total when paid`\n"


def test_given_a_1200_deep_expression_when_normalized_then_it_is_read():
    expression = " + ".join(["1"] * 1200)
    source = f"fun place(): Int {{\n    return {expression}\n}}\n"
    assert entries_of(source, "a.kt")


def test_given_a_gradle_project_when_walked_then_build_output_tests_and_scripts_are_skipped(tmp_path, monkeypatch):
    for name in [
        "src/main/kotlin/Keep.kt",
        "src/main/kotlin/com/acme/build/Builder.kt",
        "src/commonMain/kotlin/KeepToo.kt",
        "feature/src/androidMain/kotlin/Contest.kt",
        "build/generated/Generated.kt",
        "app/build/tmp/Stub.kt",
        ".gradle/cache/Cached.kt",
        ".git/objects/Tracked.kt",
        "src/commonTest/kotlin/Shared.kt",
        "src/test/kotlin/Unit.kt",
        "feature/src/androidTest/kotlin/Device.kt",
        "feature/src/testFixtures/kotlin/Fake.kt",
        "feature/testutils/Helper.kt",
        "checkout/build/src/main/kotlin/Keep.kt",
        "src/main/kotlin/FooTest.kt",
        "src/main/kotlin/FooTests.kt",
        "src/main/kotlin/FooSpec.kt",
        "build.gradle.kts",
    ]:
        write_source(tmp_path, name, "")

    def walked(folder: Path) -> list[str]:
        return [path.relative_to(tmp_path.resolve()).as_posix() for path in iter_source_files(folder)]

    assert walked(tmp_path) == [
        "feature/src/androidMain/kotlin/Contest.kt",
        "feature/testutils/Helper.kt",
        "src/commonMain/kotlin/KeepToo.kt",
        "src/main/kotlin/Keep.kt",
        "src/main/kotlin/com/acme/build/Builder.kt",
    ]
    # A package folder called `build` under `src` is code; `app/build` beside a module's `src` is not.
    src_kept = [
        "src/commonMain/kotlin/KeepToo.kt",
        "src/main/kotlin/Keep.kt",
        "src/main/kotlin/com/acme/build/Builder.kt",
    ]
    assert walked(tmp_path / "src") == src_kept
    assert walked(tmp_path / "feature" / "src") == ["feature/src/androidMain/kotlin/Contest.kt"]
    # The walked folder's name is a possible `src` parent, never a reason to skip.
    assert walked(tmp_path / "feature") == [
        "feature/src/androidMain/kotlin/Contest.kt",
        "feature/testutils/Helper.kt",
    ]
    # A project called `build`, walked from inside or named, is scanned however it is spelled.
    checkout = ["checkout/build/src/main/kotlin/Keep.kt"]
    assert walked(tmp_path / "checkout" / "build") == checkout
    assert walked(tmp_path / "checkout" / "build" / "src" / "main") == checkout
    monkeypatch.chdir(tmp_path / "src")
    assert walked(Path(".")) == walked(Path.cwd()) == src_kept
    monkeypatch.chdir(tmp_path / "checkout" / "build")
    assert walked(Path(".")) == walked(Path.cwd()) == checkout


ANNOTATED = """\
@Deprecated("old")
fun totals(orders: List<Order>): Map<String, Int> {
    val paid = orders.filter { it.status == "paid" }
    val grouped = paid.groupBy { it.customer }
    return grouped.mapValues { entry -> entry.value.sumOf { it.amount } }
}
"""


def test_given_only_an_annotation_line_edited_when_doppel_runs_with_changed_functions_then_its_function_is_in_focus(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "Orders.kt", ANNOTATED)
    write_source(tmp_path, "Report.kt", ANNOTATED)
    commit_all(tmp_path)
    write_source(tmp_path, "Orders.kt", ANNOTATED.replace('"old"', '"older"'))
    monkeypatch.chdir(tmp_path)

    assert run(["--changed-functions"]) == 0
    assert capsys.readouterr().out == "Orders.kt:1-6 totals\n  1.00  Report.kt:1-6  totals\n"


def test_given_only_a_doc_comment_edited_when_doppel_runs_with_changed_functions_then_its_function_is_not_in_focus(tmp_path, capsys, monkeypatch):
    documented = '/** Totals per customer. */\n' + ANNOTATED
    write_source(tmp_path, "Orders.kt", documented)
    write_source(tmp_path, "Report.kt", documented)
    commit_all(tmp_path)
    write_source(tmp_path, "Orders.kt", documented.replace('Totals per customer', 'Sums per customer'))
    monkeypatch.chdir(tmp_path)

    assert run(["--changed"]) == 0
    assert capsys.readouterr().out == "Orders.kt:2-7 totals\n  1.00  Report.kt:2-7  totals\n"

    assert run(["--changed-functions"]) == 0
    assert capsys.readouterr().out == "No duplicate candidates found.\n"
