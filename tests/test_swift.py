import shutil
from pathlib import Path

from doppel.cli import run
from doppel.discover import iter_source_files, spec_of
from doppel.scan import find_duplicates, scan_files
from doppel.shape import jaccard
from doppel.treesitter import end_line, parse, start_line
from helpers import commit_all, entries_of, write_source

FIXTURES = Path(__file__).parent / "fixtures"


def test_given_a_renamed_copy_when_doppel_runs_then_one_group_lists_it_with_its_score(tmp_path, capsys, monkeypatch):
    shutil.copytree(FIXTURES / "swift-renamed", tmp_path / "renamed")
    monkeypatch.chdir(tmp_path)

    assert run(["renamed"]) == 0

    assert capsys.readouterr().out == (
        "renamed/Left.swift:2-6 totals\n"
        "  1.00  renamed/Right.swift:2-6  sums\n"
    )


def candidate_spans(source: str) -> list[tuple[int, int]]:
    path = Path("a.swift")
    spec = spec_of(path)
    _data, tree = parse(source, spec.grammar(path))
    return [(start_line(node), end_line(node)) for node in spec.candidates(tree.root_node)]


def test_given_nested_functions_inits_and_computed_properties_when_picked_then_only_outer_functions_remain():
    source = """\
class Box {
    init(x: Int) {
        func inInit() {
        }
    }
    deinit {
    }
    subscript(i: Int) -> Int {
        return i
    }
    var body: Int {
        func inBody() {
        }
        return 1
    }
    var both: Int {
        get { return 1 }
        set { func inSetter() {} }
    }
    var watched = 0 {
        didSet { func inObserver() {} }
    }
    func member() {
        func inner() {
            g()
        }
        let c = { func inClosure() {} }
    }
}
protocol P {
    func noBody()
}
let top = {
    func inLambda() {
    }
}
func topLevel() {
}
"""
    assert candidate_spans(source) == [(23, 28), (37, 38)]


def score(left: str, right: str) -> float:
    entries = entries_of(left, "a.swift")
    entries += entries_of(right, "b.swift")
    assert len(entries) == 2
    return jaccard(entries[0].fingerprints, entries[1].fingerprints)


ALPHA = """\
func alpha(xs: [Int]) -> [Int] {
    // keep the odd ones
    let ys = xs.filter(odd)
    return (map)(ys, 1)
}
"""


def test_given_other_names_literals_comments_and_parentheses_when_scored_then_one():
    beta = """\
func beta(items: [Int64]) -> [Int64] {
    /* keep the even ones */
    let kept = items.filter(even)
    return map(kept, "two")
}
"""
    assert score(ALPHA, beta) == 1.0


def test_given_another_member_or_function_called_when_scored_then_below_one():
    other_member = """\
func beta(items: [Int]) -> [Int] {
    let kept = items.select(even)
    return map(kept, 2)
}
"""
    other_function = """\
func beta(items: [Int]) -> [Int] {
    let kept = items.filter(even)
    return fold(kept, 2)
}
"""
    assert score(ALPHA, other_member) < 1.0
    assert score(ALPHA, other_function) < 1.0


def function(statement: str, name: str = "alpha") -> str:
    return f"func {name}(a: Int, b: Int) {{\n    {statement}\n}}\n"


def test_given_another_subscripted_value_when_scored_then_one():
    assert score(function("let c = xs[a]"), function("let d = ys[b]", "beta")) == 1.0
    assert score(function("let c = xs.items[a]"), function("let d = ys.rows[b]", "beta")) == 1.0


def test_given_a_parenthesized_callee_when_scored_then_its_name_is_kept():
    assert score(function("(foo)(a)"), function("foo(b)", "beta")) == 1.0
    assert score(function("(foo)(a)"), function("bar(b)", "beta")) < 1.0


def test_given_another_custom_operator_when_scored_then_below_one():
    assert score(function("let c = a != b"), function("let c = a <= b", "beta")) < 1.0
    assert score(function("let c = a != b"), function("let d = b != a", "beta")) == 1.0


def test_given_another_callee_in_each_call_shape_when_scored_then_below_one():
    assert score(function("foo { }"), function("bar { }", "beta")) < 1.0
    assert score(function("let c = Set<Int>(a)"), function("let c = Array<Int>(a)", "beta")) < 1.0
    assert score(function("let c = [Int]()"), function("let c = [String]()", "beta")) < 1.0
    assert score(function("a.b.foo(a)"), function("a.b.bar(a)", "beta")) < 1.0
    assert score(function("let c = .some(a)"), function("let c = .other(a)", "beta")) < 1.0


def test_given_another_keyword_when_scored_then_below_one():
    assert score(function("return a"), function("throw a", "beta")) < 1.0
    plain = "func alpha(a: Int) {\n    h(a)\n}\n"
    assert score(plain, plain.replace(") {", ") async {")) < 1.0
    assert score(plain, plain.replace(") {", ") rethrows {")) < 1.0
    assert score(function("let c = a as? Int"), function("let c = a as! Int", "beta")) < 1.0
    assert score(function("let c = try? f(a)"), function("let c = try! f(a)", "beta")) < 1.0
    break_outer = "outer: for c in [a] { break outer }"
    continue_outer = "outer: for c in [a] { continue outer }"
    assert score(function(break_outer), function(continue_outer, "beta")) < 1.0


def test_given_a_swapped_modifier_when_scored_then_one():
    assert score("private " + function("return a"), "public " + function("return b", "beta")) == 1.0


def test_given_another_call_in_an_interpolation_when_scored_then_below_one():
    assert score(function('return "sum \\(foo(a))"'), function('return "sum \\(bar(a))"', "beta")) < 1.0
    assert score(function('return #"sum \\#(foo(a))"#'), function('return #"sum \\#(bar(a))"#', "beta")) < 1.0


def test_given_other_plain_string_text_when_scored_then_one():
    assert score(function('return "left"'), function('return "right"', "beta")) == 1.0
    assert score(function('return "left \\(foo(a))"'), function('return "right \\(foo(b))"', "beta")) == 1.0


def pairs(root: Path, threshold: float = 0.99):
    files = sorted(path for path in root.rglob("*") if path.is_file())
    entries, _broken, _unreadable = scan_files(files, root, min_lines=1, min_nodes=1)
    return find_duplicates(entries, threshold)


LEFT = """\
func alpha(xs: [Int]) -> [Int] {
    let ys = filter(xs, odd)
    return map(ys, inc)
}
"""


def test_given_an_extra_statement_when_paired_then_below_one(tmp_path):
    write_source(tmp_path, "a.swift", LEFT)
    write_source(
        tmp_path,
        "b.swift",
        """\
func beta(items: [Int]) -> [Int] {
    let kept = filter(items, even)
    let extra = filter(kept, even)
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
        "a.swift",
        """\
func alpha(xs: [Int]) -> Int {
    var ys = Array<String>()
    ys.append(xs)
    return xs.total
}
""",
    )
    write_source(
        tmp_path,
        "b.swift",
        """\
func beta(items: [Int]) -> Int {
    var kept = Array<Int64>()
    kept.append(items)
    return items.count
}
""",
    )
    found = pairs(tmp_path)
    assert [(item.left.file, item.right.file, item.score) for item in found] == [("a.swift", "b.swift", 1.0)]


def test_given_a_constructor_call_when_normalized_then_its_type_is_kept():
    for call, kept in [
        ("[Int]()", '"Int"'),
        ("[String: Int]()", '"String"'),
        ("Set<Int>()", '"Set"'),
        ("Foo.Bar()", '"Bar"'),
    ]:
        source = f"func alpha() {{\n    let ys = {call}\n}}\n"
        [entry] = entries_of(source, "a.swift")
        assert kept in entry.fingerprints, call


def test_given_a_nested_function_when_paired_then_the_outer_functions_pair_scoring_one(tmp_path):
    write_source(
        tmp_path,
        "a.swift",
        """\
func alpha(xs: [Int]) -> [Int] {
    func inner(ys: [Int]) -> [Int] {
        return filter(ys, odd)
    }
    return inner(ys: xs)
}
""",
    )
    write_source(
        tmp_path,
        "b.swift",
        """\
func beta(items: [Int]) -> [Int] {
    func inner(kept: [Int]) -> [Int] {
        return filter(kept, even)
    }
    return inner(kept: items)
}
""",
    )
    found = pairs(tmp_path)
    assert len(found) == 1
    assert found[0].score == 1.0
    assert (found[0].left.start_line, found[0].left.end_line) == (1, 6)


def test_given_five_copies_when_paired_then_ten_pairs(tmp_path):
    for index in range(5):
        write_source(tmp_path, f"copy{index}.swift", LEFT)
    found = pairs(tmp_path)
    assert len(found) == 10
    assert all(item.score == 1.0 for item in found)


def test_given_each_function_shape_when_extracted_then_its_name_is_the_name_the_source_writes():
    source = """\
func plain(a: Int) -> Int {
}
func generic<T>(x: T) -> T {
}
func `default`() {
}
struct Money {
    static func == (left: Money, right: Money) -> Bool {
    }
}
infix operator <=> : ComparisonPrecedence
func <=> (left: Int, right: Int) -> Int {
}
"""
    assert [entry.name for entry in entries_of(source, "a.swift")] == ["plain", "generic", "`default`", "==", "<=>"]


def test_given_two_copied_equality_operators_when_doppel_runs_then_their_lines_show_the_operator(tmp_path, capsys, monkeypatch):
    source = """\
struct {type} {{
    static func == (left: {type}, right: {type}) -> Bool {{
        let same = left.amount == right.amount && left.currency == right.currency
        return same && left.rounded(2) == right.rounded(2)
    }}
}}
"""
    write_source(tmp_path, "Money.swift", source.format(type="Money"))
    write_source(tmp_path, "Price.swift", source.format(type="Price"))
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0
    assert capsys.readouterr().out == "Money.swift:2-5 ==\n  1.00  Price.swift:2-5  ==\n"


def test_given_a_1200_deep_expression_when_normalized_then_it_is_read():
    expression = " + ".join(["1"] * 1200)
    source = f"func place() -> Int {{\n    return {expression}\n}}\n"
    assert entries_of(source, "a.swift")


def test_given_a_swift_project_when_walked_then_output_dependencies_and_tests_are_skipped(tmp_path, monkeypatch):
    for name in [
        "Sources/App/Keep.swift",
        "Sources/App/Contest.swift",
        "App/Feature/KeepToo.swift",
        ".build/checkouts/Dep/Sources/Dep.swift",
        "Packages/Core/.build/release/Gen.swift",
        "target/coverage/swift/DerivedData/SourcePackages/checkouts/Dep/Dep.swift",
        "Pods/Lib/Lib.swift",
        "Carthage/Checkouts/Lib/Lib.swift",
        ".git/objects/Tracked.swift",
        "Tests/AppTests/Unit.swift",
        "AppUITests/Flow.swift",
        "Packages/Core/Tests/CoreTests/Core.swift",
        "Sources/App/FooTests.swift",
        "Package.swift",
    ]:
        write_source(tmp_path, name, "")

    def walked(folder: Path) -> list[str]:
        return [path.relative_to(tmp_path.resolve()).as_posix() for path in iter_source_files(folder)]

    assert walked(tmp_path) == [
        "App/Feature/KeepToo.swift",
        "Package.swift",
        "Sources/App/Contest.swift",
        "Sources/App/Keep.swift",
    ]
    # The walked folder's name is context, never a reason to skip.
    assert walked(tmp_path / "Tests" / "AppTests") == ["Tests/AppTests/Unit.swift"]
    assert walked(tmp_path / "AppUITests") == ["AppUITests/Flow.swift"]
    monkeypatch.chdir(tmp_path / "AppUITests")
    assert walked(Path(".")) == ["AppUITests/Flow.swift"]


ANNOTATED = """\
@discardableResult
func totals(orders: [Order]) -> [String: Int] {
    let paid = orders.filter { $0.status == "paid" }
    let grouped = Dictionary(grouping: paid) { $0.customer }
    return grouped.mapValues { rows in rows.reduce(0) { $0 + $1.amount } }
}
"""


def test_given_only_an_annotation_line_edited_when_doppel_runs_with_changed_functions_then_its_function_is_in_focus(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "Orders.swift", ANNOTATED)
    write_source(tmp_path, "Report.swift", ANNOTATED)
    commit_all(tmp_path)
    write_source(tmp_path, "Orders.swift", ANNOTATED.replace("@discardableResult", "@inlinable"))
    monkeypatch.chdir(tmp_path)

    assert run(["--changed-functions"]) == 0
    assert capsys.readouterr().out == "Orders.swift:1-6 totals\n  1.00  Report.swift:1-6  totals\n"


def test_given_only_a_doc_comment_edited_when_doppel_runs_with_changed_functions_then_its_function_is_not_in_focus(tmp_path, capsys, monkeypatch):
    documented = '/// Totals per customer.\n' + ANNOTATED
    write_source(tmp_path, "Orders.swift", documented)
    write_source(tmp_path, "Report.swift", documented)
    commit_all(tmp_path)
    write_source(tmp_path, "Orders.swift", documented.replace('Totals per customer', 'Sums per customer'))
    monkeypatch.chdir(tmp_path)

    assert run(["--changed"]) == 0
    assert capsys.readouterr().out == "Orders.swift:2-7 totals\n  1.00  Report.swift:2-7  totals\n"

    assert run(["--changed-functions"]) == 0
    assert capsys.readouterr().out == "No duplicate candidates found.\n"
