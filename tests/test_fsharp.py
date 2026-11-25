import re
import shutil
from pathlib import Path

import pytest

from doppel.cli import run
from doppel.discover import iter_source_files
from doppel.shape import jaccard
from helpers import commit_all, entries_of, write_source

FIXTURES = Path(__file__).parent / "fixtures"


def test_given_a_renamed_copy_when_doppel_runs_then_one_group_lists_it_with_its_score(tmp_path, capsys, monkeypatch):
    shutil.copytree(FIXTURES / "fsharp-renamed", tmp_path / "renamed")
    monkeypatch.chdir(tmp_path)

    assert run(["renamed"]) == 0

    assert capsys.readouterr().out == (
        "renamed/Left.fs:3-6 totals\n"
        "  1.00  renamed/Right.fs:3-6  sums\n"
    )


def score(left: str, right: str) -> float:
    entries = entries_of(left, "a.fs")
    entries += entries_of(right, "b.fs")
    assert len(entries) == 2
    return jaccard(entries[0].fingerprints, entries[1].fingerprints)


ALPHA = """\
let alpha (xs: int list) =
    // keep the odd ones
    let ys = List.filter isOdd xs
    compute ys 1
"""


def test_given_other_names_literals_and_comments_when_scored_then_one():
    beta = """\
let beta (items: int64 list) =
    (* keep the even ones *)
    let kept = List.filter isOdd items
    compute kept "two"
"""
    assert score(ALPHA, beta) == 1.0


def test_given_another_function_called_when_scored_then_below_one():
    other_function = """\
let beta (items: int list) =
    let kept = List.filter isOdd items
    combine kept 1
"""
    other_member = """\
let beta (items: int list) =
    let kept = List.choose isOdd items
    compute kept 1
"""
    assert score(ALPHA, other_function) < 1.0
    assert score(ALPHA, other_member) < 1.0


def test_given_a_function_of_a_recursive_group_when_scored_against_its_copy_as_a_plain_let_then_one():
    group = """\
let rec isEven n =
    if n = 0 then true
    else isOdd (n - 1)
and isOdd n =
    // the other half
    if n = 0 then false
    else isEven (n - 1)
"""
    plain = """\
let isOddToo m =
    if m = 0 then false
    else isEven (m - 1)
"""
    first, second = entries_of(group, "a.fs")
    [copy] = entries_of(plain, "b.fs")
    assert jaccard(second.fingerprints, copy.fingerprints) == 1.0
    assert jaccard(first.fingerprints, copy.fingerprints) < 1.0


def grouped(index: int, keyword: str, name: str) -> str:
    """A function that differs from those of other indexes by the functions it calls."""

    lines = "\n".join(f"    let step{step} = transform{index}x{step} step{step - 1}" for step in range(1, index + 2))
    return f"{keyword} {name}{index} step0 =\n{lines}\n    finish{index} step{index + 1}\n"


def test_given_a_ten_function_group_when_doppel_runs_then_each_function_is_listed_under_its_own_name_and_lines(tmp_path, capsys, monkeypatch):
    group = "\n".join(grouped(index, "and" if index else "let rec", "member") for index in range(10))
    write_source(tmp_path, "Group.fs", group)
    write_source(tmp_path, "Plain.fs", "\n".join(grouped(index, "let", "copy") for index in range(10)))
    monkeypatch.chdir(tmp_path)

    assert run(["--min-lines", "1", "--min-nodes", "1"]) == 0

    groups = []
    start = 1
    for index in range(10):
        end = start + index + 2
        plain_start = start
        groups.append(f"Group.fs:{start}-{end} member{index}\n  1.00  Plain.fs:{plain_start}-{end}  copy{index}\n")
        start = end + 2
    assert capsys.readouterr().out == "\n".join(groups)


def names_and_lines(source: str) -> list[tuple[str | None, int]]:
    return [(entry.name, entry.start_line) for entry in entries_of(source, "a.fs")]


def test_given_functions_with_a_return_type_or_an_attribute_after_and_when_picked_then_each_is_listed_under_its_name():
    source = """\
let short x : int = x + 1
let private total (orders: Order list) : decimal =
    orders
    |> List.sumBy amount
let rec even n : bool =
    n = 0 || odd (n - 1)
and odd n : bool =
    n <> 0 && even (n - 1)
and [<Obsolete>] third n =
    even n
and [<Obsolete>] fourth (n: int) m : int =
    odd n
let onClick _ = refresh 1
"""
    assert names_and_lines(source) == [
        ("short", 1),
        ("total", 2),
        ("even", 5),
        ("odd", 7),
        ("third", 9),
        ("fourth", 11),
        ("onClick", 13),
    ]


def test_given_an_access_modifier_and_a_return_type_on_the_last_binding_when_picked_then_the_function_is_listed():
    # Last in its source, each head is a `value_declaration_left`.
    sources = {
        "let private f x : int =\n    x\n": [("f", 1)],
        "let internal g (x: int) : int =\n    x\n": [("g", 1)],
        "let rec private f a b : int =\n    a + b\n": [("f", 1)],
        "module M =\n    let private f x : int =\n        x\n": [("f", 2)],
        "let rec a x =\n    b x\nand private b x : int =\n    x\n": [("a", 1), ("b", 3)],
    }
    for source, expected in sources.items():
        assert names_and_lines(source) == expected, source


def test_given_an_attribute_then_a_modifier_after_and_when_picked_then_the_function_is_listed_under_its_name():
    source = """\
let rec a x =
    b x
and [<Obsolete>] private b x : int =
    x
and [<Obsolete>] inline c x =
    x
and [<Obsolete>] internal d = 3
and [<Obsolete>] inline private e x : int =
    x
and [<Obsolete>] private inline f x y =
    x
"""
    assert names_and_lines(source) == [("a", 1), ("b", 3), ("c", 5), ("e", 8), ("f", 10)]


def test_given_typed_and_destructuring_values_and_let_bang_when_picked_then_none_is_a_function():
    source = """\
let count : int = 3
let table: Map<string, int> = Map.empty
let Some y = opt
let Ok(value) = result
let (Some z) = opt
let (a: int), b = 1, 2
let rec first : int = 1
and [<Literal>] Second = 2
let run =
    task {
        let! response = fetch ()
        use! stream = open response
        let Some w = response
        return w
    }
"""
    assert names_and_lines(source) == []


def test_given_a_function_nested_in_a_function_a_lambda_or_a_member_when_picked_then_it_is_left_out():
    in_function = """\
let outer x =
    let inner y = y + 1
    inner x
"""
    in_lambdas = """\
let handlers = [
    fun x -> (let inLambda y = y in inLambda x)
    function
    | A -> (let inFunction y = y in inFunction 1)
    | _ -> 0
]
"""
    in_member = """\
type Box() =
    member _.Run x =
        let inMember y = y
        inMember x
"""
    assert names_and_lines(in_function) == [("outer", 1)]
    assert names_and_lines(in_lambdas) == []
    assert names_and_lines(in_member) == [("Run", 2)]


def test_given_a_function_defined_inside_a_top_level_value_when_picked_then_it_is_listed():
    source = """\
let tests =
    testList "totals" [
        let helper z = z * 2
        testCase "doubles" <| fun () -> helper 1 |> ignore
    ]
"""
    assert names_and_lines(source) == [("helper", 3)]


@pytest.mark.parametrize(
    ("head", "expected"),
    [("let total (orders: Order list)", 29 / 31), ("let total orders", 21 / 25)],
)
def test_given_a_copy_differing_only_by_a_return_type_when_scored_then_the_score_is_pinned(head, expected):
    # Heads are given as name, parameters and return type, so the type is the
    # only difference: the grammar reads the body's last name (`amount`) one
    # `long_identifier` deeper in one of the two, which the spec unwraps.
    untyped = f"""\
{head} =
    orders
    |> List.filter isPaid
    |> List.sumBy amount
"""
    typed = untyped.replace(" =\n", " : decimal =\n", 1)
    assert score(typed, untyped) == expected


def ranges(source: str) -> list[tuple[str | None, int, int]]:
    return [(entry.name, entry.start_line, entry.end_line) for entry in entries_of(source, "a.fs")]


def test_given_attributes_and_the_next_function_s_doc_comment_when_picked_then_each_function_runs_from_its_attribute_to_its_body_s_end():
    # The grammar ends each function at the doc comment of the next.
    source = """\
[<Obsolete>]
let first x =
    x + 1

/// Doc for second.
[<Obsolete>]
[<CompiledName("Second")>]
let rec second x =
    third x
/// Doc for third.
and [<Obsolete>] third x =
    second x

module Inner =
    /// Doc for fourth.
    [<Obsolete>]
    let fourth x =
        x
"""
    assert ranges(source) == [
        ("first", 1, 3),
        ("second", 6, 9),
        ("third", 11, 12),
        ("fourth", 16, 18),
    ]


DOCUMENTED = """\
let rec walk node =
    match node with
    | Leaf value -> visit value
    | Branch children -> List.iter walk children
/// Walks the leaves only.
and [<Obsolete>] leaves node =
    match node with
    | Leaf value -> [ value ]
    | Branch children -> List.collect leaves children

/// Totals per customer.
[<Obsolete>]
let totals (orders: Order list) =
    orders
    |> List.filter isPaid
    |> List.groupBy customer
    |> List.map summarize
"""


def run_changed_functions(tmp_path, monkeypatch, edited: str) -> int:
    write_source(tmp_path, "Orders.fs", DOCUMENTED)
    write_source(tmp_path, "Report.fs", DOCUMENTED)
    commit_all(tmp_path)
    write_source(tmp_path, "Orders.fs", edited)
    monkeypatch.chdir(tmp_path)
    return run(["--changed-functions"])


def test_given_only_a_doc_comment_edited_when_doppel_runs_with_changed_functions_then_no_function_is_in_focus(tmp_path, capsys, monkeypatch):
    # The grammar holds each doc comment inside the function above it.
    edits = [("Totals per customer", "Sums per customer"), ("Walks the leaves only", "Walks each leaf")]
    for index, (old, new) in enumerate(edits):
        assert run_changed_functions(tmp_path / str(index), monkeypatch, DOCUMENTED.replace(old, new)) == 0
        assert capsys.readouterr().out == "No duplicate candidates found.\n", old


def test_given_only_an_attribute_edited_when_doppel_runs_with_changed_functions_then_its_function_is_in_focus(tmp_path, capsys, monkeypatch):
    cases = {
        "[<Obsolete>]\nlet totals": "Orders.fs:12-17 totals\n  1.00  Report.fs:12-17  totals\n",
        "and [<Obsolete>] leaves": "Orders.fs:6-9 leaves\n  1.00  Report.fs:6-9  leaves\n",
    }
    for index, (old, expected) in enumerate(cases.items()):
        edited = DOCUMENTED.replace(old, old.replace("Obsolete", "Deprecated"))
        assert run_changed_functions(tmp_path / str(index), monkeypatch, edited) == 0
        assert capsys.readouterr().out == expected, old


def test_given_two_line_functions_followed_by_blank_lines_and_a_comment_when_doppel_runs_then_they_stay_under_min_lines(tmp_path, capsys, monkeypatch):
    # The grammar holds the comment inside `total`, and inside the last `match` rule of `pick`.
    source = """\
let total orders =
    orders |> List.sumBy amount


// Pick a rule by its value.

let pick x =
    match x with | Some v -> keep v | None -> drop ()


// Last words.
"""
    write_source(tmp_path, "Left.fs", source)
    write_source(tmp_path, "Right.fs", source)
    monkeypatch.chdir(tmp_path)

    assert run(["--min-nodes", "1"]) == 0
    assert capsys.readouterr().out == "No duplicate candidates found.\n"

    assert run(["--min-nodes", "1", "--min-lines", "2"]) == 0
    assert capsys.readouterr().out == (
        "Left.fs:1-2 total\n  1.00  Right.fs:1-2  total\n\nLeft.fs:7-8 pick\n  1.00  Right.fs:7-8  pick\n"
    )


def bodies_score(left: str, right: str) -> float:
    return score(f"let alpha a xs ys =\n    {left}\n", f"let beta a xs ys =\n    {right}\n")


@pytest.mark.parametrize("operator", ["+", "|>", "<|", "::"])
def test_given_another_function_called_after_an_operator_when_scored_then_below_one(operator):
    # `a + f x` is read as `(a + f) x`: the function called is the operator's right operand.
    assert bodies_score(f"a {operator} f xs", f"a {operator} g xs") < 1.0
    assert bodies_score(f"a {operator} f xs", f"a {operator} f ys") == 1.0


def test_given_a_parenthesized_operation_heading_a_call_when_another_function_is_in_it_then_below_one():
    assert bodies_score("(a + f) xs", "(a + g) xs") < 1.0
    assert bodies_score("(a + f) xs", "(a + f) ys") == 1.0


@pytest.mark.parametrize(("left", "right"), [("a + xs", "a - xs"), ("a :: xs", "a @ xs")])
def test_given_another_operator_between_the_same_operands_when_scored_then_below_one(left, right):
    assert bodies_score(left, right) < 1.0


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("xs |> List.length", "xs |> List.sum"),
        ("(xs, ys) ||> List.zip", "(xs, ys) ||> List.allPairs"),
        ("List.length <| xs", "List.sum <| xs"),
        ("List.length >> string", "List.sum >> string"),
        ("string >> List.length", "string >> List.sum"),
        ("List.length << string", "List.sum << string"),
        ("string << List.length", "string << List.sum"),
    ],
)
def test_given_another_function_piped_or_composed_with_nothing_after_it_when_scored_then_below_one(left, right):
    assert bodies_score(left, right) < 1.0


PIPELINE = """\
let alpha (orders: Order list) =
    orders
    |> List.filter isPaid
    |> List.map amount
    |> List.sum
"""


def test_given_a_pipeline_differing_in_its_middle_stage_when_scored_then_below_one():
    assert score(PIPELINE, PIPELINE.replace("List.map", "List.collect")) < 1.0


def test_given_a_pipeline_with_other_locals_and_a_comment_between_stages_when_scored_then_one():
    renamed = """\
let beta (rows: Row list) =
    rows
    // only what was paid
    |> List.filter settled
    |> List.map total
    |> List.sum
"""
    assert score(PIPELINE, renamed) == 1.0


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("a.Method(xs)", "a.Other(xs)"),
        ("xs.Foo(1).Bar 2", "xs.Foo(1).Baz 2"),
        ("xs.Foo(1).Bar 2", "xs.Qux(1).Bar 2"),
        ("-a", "+a"),
    ],
)
def test_given_another_method_or_prefix_operator_when_scored_then_below_one(left, right):
    assert bodies_score(left, right) < 1.0


def test_given_methods_and_properties_on_a_type_when_picked_then_each_method_is_listed_under_its_last_name_part():
    source = """\
type Calc(seed: int) =
    member this.Add(a: int, b: int) = a + b
    member _.Twice x y : int = x * y
    static member Create (x: int) = Calc(x)
    override this.ToString() = "calc"
    static member (+) (a: Calc, b: Calc) = a
    member private this.Hidden (x: int) : int =
        x + 1
    member private inline this.Fast x = x
    member _.Value = seed
    member this.Typed : int = seed
    member this.Prop with get () = seed and set (v: int) = ()
    member val Auto = 1 with get, set
    abstract member Run : int -> int
    default this.Run x = x
    interface System.IDisposable with
        member this.Dispose() = ()
"""
    assert names_and_lines(source) == [
        ("Add", 2),
        ("Twice", 3),
        ("Create", 4),
        ("ToString", 5),
        ("(+)", 6),
        ("Hidden", 7),
        ("Fast", 9),
        ("Run", 15),
        ("Dispose", 17),
    ]


METHOD = """\
type Orders(rows: Order list) =
    member this.Total (customer: string) =
        // only what was paid
        rows
        |> List.filter (isPaidBy customer)
        |> List.sumBy amount
"""


def test_given_a_copied_method_when_scored_then_one():
    copy = """\
type Ledger(items: Entry list) =
    member self.Sum (who: int) =
        items
        |> List.filter (isPaidBy who)
        |> List.sumBy amount
"""
    assert score(METHOD, copy) == 1.0


def test_given_a_method_calling_another_function_when_scored_then_below_one():
    assert score(METHOD, METHOD.replace("List.sumBy", "List.averageBy")) < 1.0
    assert score(METHOD, METHOD.replace("isPaidBy", "isOwedBy")) < 1.0


DOCUMENTED_TYPE = """\
type Orders(rows: Order list) =
    /// Totals per customer.
    [<Obsolete>]
    member this.Totals (customer: string) =
        rows
        |> List.filter (isPaidBy customer)
        |> List.groupBy day
        |> List.map summarize
    /// Counts per customer.
    [<Obsolete>]
    static member Counts (rows: Order list) =
        rows
        |> List.filter isPaid
        |> List.countBy customer
        |> List.sortBy snd
"""


def run_changed_members(tmp_path, monkeypatch, edited: str) -> int:
    write_source(tmp_path, "Orders.fs", DOCUMENTED_TYPE)
    write_source(tmp_path, "Report.fs", DOCUMENTED_TYPE)
    commit_all(tmp_path)
    write_source(tmp_path, "Orders.fs", edited)
    monkeypatch.chdir(tmp_path)
    return run(["--changed-functions"])


def test_given_only_a_member_s_doc_comment_edited_when_doppel_runs_with_changed_functions_then_no_function_is_in_focus(tmp_path, capsys, monkeypatch):
    # The grammar holds the second doc comment inside the member above it.
    edits = [("Totals per customer", "Sums per customer"), ("Counts per customer", "Tallies per customer")]
    for index, (old, new) in enumerate(edits):
        assert run_changed_members(tmp_path / str(index), monkeypatch, DOCUMENTED_TYPE.replace(old, new)) == 0
        assert capsys.readouterr().out == "No duplicate candidates found.\n", old


def test_given_only_a_member_s_attribute_edited_when_doppel_runs_with_changed_functions_then_the_member_is_in_focus(tmp_path, capsys, monkeypatch):
    cases = {
        "[<Obsolete>]\n    member": "Orders.fs:3-8 Totals\n  1.00  Report.fs:3-8  Totals\n",
        "[<Obsolete>]\n    static": "Orders.fs:10-15 Counts\n  1.00  Report.fs:10-15  Counts\n",
    }
    for index, (old, expected) in enumerate(cases.items()):
        edited = DOCUMENTED_TYPE.replace(old, old.replace("Obsolete", "Deprecated"))
        assert run_changed_members(tmp_path / str(index), monkeypatch, edited) == 0
        assert capsys.readouterr().out == expected, old


def test_given_values_whose_right_side_is_a_lambda_when_picked_then_each_is_listed_under_its_name():
    source = """\
let add = fun a (b: int) ->
    a + b
let describe = function
    | Some x -> show x
    | None -> "none"
let private apply : int -> int = fun x -> x
let rec even = fun n -> n = 0 || odd (n - 1)
and [<Obsolete>] odd = function
    | 0 -> false
    | n -> even (n - 1)
[<Obsolete>]
let unit = fun () -> 1
"""
    assert ranges(source) == [
        ("add", 1, 2),
        ("describe", 3, 5),
        ("apply", 6, 6),
        ("even", 7, 7),
        ("odd", 8, 10),
        ("unit", 11, 12),
    ]


FUN_VALUE = """\
let total = fun (orders: Order list) customer ->
    // only what was paid
    orders
    |> List.filter (isPaidBy customer)
    |> List.sumBy amount
"""

FUNCTION_VALUE = """\
let describe = function
    | Some order -> show order.Total
    | None -> "none"
"""


def test_given_a_copied_lambda_value_when_scored_then_one():
    fun_copy = """\
let sum = fun (rows: Row list) who ->
    rows
    |> List.filter (isPaidBy who)
    |> List.sumBy amount
"""
    function_copy = """\
let explain = function
    | Some row -> show row.Count
    | None -> ""
"""
    assert score(FUN_VALUE, fun_copy) == 1.0
    assert score(FUNCTION_VALUE, function_copy) == 1.0


def test_given_a_value_holding_a_lambda_further_in_when_picked_then_nothing_is():
    source = """\
let handlers = [ fun x -> x + 1; fun x -> x * 2 ]
let pair = (fun x -> x), (function | 0 -> 1 | n -> n)
let wrapped = (fun x -> x)
let logged = withLogging (fun x -> x)
let piped = id <| fun x -> x
"""
    assert names_and_lines(source) == []


def test_given_a_fun_value_and_its_copy_written_the_plain_way_when_scored_then_one():
    plain = """\
let total (orders: Order list) customer =
    // only what was paid
    orders
    |> List.filter (isPaidBy customer)
    |> List.sumBy amount
"""
    assert score(FUN_VALUE, plain) == 1.0


def test_given_a_function_value_and_its_copy_written_with_match_when_scored_then_the_score_is_pinned():
    # `match value with` adds the parameter and the matched expression.
    plain = """\
let describe value =
    match value with
    | Some order -> show order.Total
    | None -> "none"
"""
    assert score(FUNCTION_VALUE, plain) == 23 / 27


def test_given_a_project_when_walked_then_build_output_and_tests_are_skipped(tmp_path, monkeypatch):
    for name in [
        "src/Billing/Invoice.fs",
        "src/Billing/Latest.fs",
        "src/Contest/Entry.fs",
        "src/Billing/bin/Debug/net8.0/Gen.fs",
        "src/Billing/obj/Debug/net8.0/AssemblyInfo.fs",
        "test/Harness.fs",
        "tests/Program.fs",
        "src/Billing.Tests/Fixtures.fs",
        "src/Core.UnitTest/Fixtures.fs",
        "src/Billing/InvoiceTest.fs",
        "src/Billing/InvoiceTests.fs",
        "src/Billing/Tests.md",
    ]:
        write_source(tmp_path, name, "")

    def walked(path: Path) -> list[str]:
        return [found.relative_to(tmp_path.resolve()).as_posix() for found in iter_source_files(path)]

    # Matching is case-sensitive: `Latest.fs` and `Contest` are code.
    assert walked(tmp_path) == [
        "src/Billing/Invoice.fs",
        "src/Billing/Latest.fs",
        "src/Contest/Entry.fs",
    ]
    # A path named as an argument is compared; the walked folder's name is context only.
    assert walked(tmp_path / "src" / "Billing" / "InvoiceTests.fs") == ["src/Billing/InvoiceTests.fs"]
    assert walked(tmp_path / "tests") == ["tests/Program.fs"]
    assert walked(tmp_path / "src" / "Billing.Tests") == ["src/Billing.Tests/Fixtures.fs"]
    monkeypatch.chdir(tmp_path / "test")
    assert walked(Path(".")) == ["test/Harness.fs"]


TOTALS = """\
let totals (orders: Order list) =
    orders
    |> List.filter isPaid
    |> List.groupBy customer
    |> List.map summarize
"""

RANK = """\
let rank (scores: Score list) =
    scores
    |> List.sortByDescending points
    |> List.truncate 10
    |> List.mapi place
"""


def write_project(root: Path) -> None:
    write_source(root, "src/Orders.fs", TOTALS)
    write_source(root, "src/Report.fs", TOTALS)
    write_source(root, "src/Board.fs", RANK)
    write_source(root, "src/Table.fs", RANK)
    write_source(root, "tests/OrdersTests.fs", TOTALS)


def test_given_an_edited_file_when_doppel_runs_with_changed_then_only_its_copies_are_listed(tmp_path, capsys, monkeypatch):
    write_project(tmp_path)
    commit_all(tmp_path)
    write_source(tmp_path, "src/Report.fs", TOTALS.replace("orders", "rows"))
    monkeypatch.chdir(tmp_path)

    assert run(["--changed"]) == 0
    assert capsys.readouterr().out == "src/Report.fs:1-5 totals\n  1.00  src/Orders.fs:1-5  totals\n"


def test_given_files_named_with_focus_when_doppel_runs_then_only_their_copies_are_listed(tmp_path, capsys, monkeypatch):
    write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert run(["--focus", "src/Board.fs"]) == 0
    assert capsys.readouterr().out == "src/Board.fs:1-5 rank\n  1.00  src/Table.fs:1-5  rank\n"

    # A test file named this way heads a group with the code it copies.
    assert run(["--focus", "tests/OrdersTests.fs"]) == 0
    assert capsys.readouterr().out == (
        "tests/OrdersTests.fs:1-5 totals\n"
        "  1.00  src/Orders.fs:1-5  totals\n"
        "  1.00  src/Report.fs:1-5  totals\n"
    )


SHADER = """\
varying vec2 uv;
uniform sampler2D image;

void main() {
    vec4 sum = texture2D(image, uv) * 0.5;
    sum += texture2D(image, uv + vec2(0.01, 0.0)) * 0.25;
    sum += texture2D(image, uv - vec2(0.01, 0.0)) * 0.25;
    gl_FragColor = sum;
}
"""


def run_on_shader(root: Path, monkeypatch, capsys, source: str) -> list[str]:
    """Standard error of doppel run, with no minimum size, on one GLSL shader ending in `.fs`."""

    write_source(root, "shaders/blur.fs", source)
    monkeypatch.chdir(root)
    assert run(["--min-lines", "1", "--min-nodes", "1"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "No duplicate candidates found.\n"
    return captured.err.splitlines()


def test_given_a_glsl_shader_the_grammar_cannot_parse_when_doppel_runs_then_it_is_named_counted_and_yields_no_function(tmp_path, capsys, monkeypatch):
    # The `#version` directive is what the F# grammar rejects.
    source = "#version 330 core\n\n" + SHADER
    assert entries_of(source, "blur.fs") == []

    err = run_on_shader(tmp_path, monkeypatch, capsys, source)

    assert err[0] == "doppel: shaders/blur.fs has parse errors; compared as parsed"
    assert re.fullmatch(r"doppel: 1 file scanned, 0 functions compared, 1 file with parse errors, \d+\.\d\ds", err[1])
    assert len(err) == 2


def test_given_a_glsl_shader_the_grammar_parses_when_doppel_runs_then_it_yields_no_function(tmp_path, capsys, monkeypatch):
    assert entries_of(SHADER, "blur.fs") == []

    err = run_on_shader(tmp_path, monkeypatch, capsys, SHADER)

    assert re.fullmatch(r"doppel: 1 file scanned, 0 functions compared, 0 files with parse errors, \d+\.\d\ds", err[0])
    assert len(err) == 1


EVEN_ODD = """\
let (|Even|Odd|) n =
    if n % 2 = 0 then Even else Odd
"""

ACTIVE_PATTERNS = EVEN_ODD + """
let (|Int|_|) (text: string) : int option =
    tryParse text
let rec (|Leaf|) node : int =
    leafOf node
"""


def test_given_active_patterns_when_picked_then_each_is_listed_under_its_pattern_as_written():
    assert names_and_lines(ACTIVE_PATTERNS) == [("(|Even|Odd|)", 1), ("(|Int|_|)", 4), ("(|Leaf|)", 6)]


def test_given_a_renamed_copy_of_an_active_pattern_when_scored_then_one():
    copy = """\
let (|Small|Large|) size =
    if size % 9 = 4 then Small else Large
"""
    assert score(EVEN_ODD, copy) == 1.0


@pytest.mark.parametrize(
    ("wildcard", "named"),
    [
        ("let f _ x = g x\n", "let f a x = g x\n"),
        ("let rec f _ x : int =\n    g x\n", "let rec f a x : int =\n    g x\n"),
        ("let f = fun _ x -> g x\n", "let f a x = g x\n"),
    ],
)
def test_given_a_wildcard_parameter_when_scored_against_a_named_one_then_one(wildcard, named):
    assert score(wildcard, named) == 1.0


def test_given_a_union_case_destructured_with_a_wildcard_when_picked_then_it_is_not_a_function():
    source = """\
let Some _ = opt
let Ok _ = result
let rec Error _ = failure
"""
    assert names_and_lines(source) == []


def test_given_a_match_on_one_line_and_on_several_when_scored_then_the_score_is_pinned():
    # The grammar reads the rules after the first as operators in its body.
    one_line = 'let describe value = match value with | Some order -> show order | None -> "none"\n'
    several = """\
let describe value =
    match value with
    | Some order -> show order
    | None -> "none"
"""
    assert score(one_line, several) == 9 / 17
