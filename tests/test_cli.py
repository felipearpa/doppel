import os
import re
import shutil
import sys
from pathlib import Path

import pytest

from doppel.cli import run
from doppel.treesitter import parser_for
from helpers import commit_all, git, write_source

FIXTURES = Path(__file__).parent / "fixtures"

TOTALS = """\
fun totals(orders: List<Order>): Map<String, Int> {
    val paid = orders.filter { it.status == "paid" }
    val grouped = paid.groupBy { it.customer }
    return grouped.mapValues { entry -> entry.value.sumOf { it.amount } + 10 }
}
"""

SHORT = """\
fun short(a: Int): Int {
    return listOf(a, a + 1).map { it * 2 }.filter { it > 3 }.sum()
}
"""


def listed_groups(out: str) -> list[tuple[str, list[str]]]:
    """The file of each group's heading and of each copy under it, in the printed order.

    A name, when printed, follows the location.
    """

    groups = []
    for block in re.findall(r"^\S.*(?:\n  .*)*", out, flags=re.MULTILINE):
        heading, *copies = block.splitlines()
        if heading == "No duplicate candidates found.":
            continue
        groups.append(
            (
                re.fullmatch(r"(\S+):\d+-\d+(?: \S.*)?", heading)[1],
                [re.fullmatch(r"  \d\.\d\d  (\S+):\d+-\d+(?:  \S.*)?", copy)[1] for copy in copies],
            )
        )
    return groups


def project(root: Path) -> None:
    write_source(root, "Orders.kt", TOTALS)
    write_source(root, "Report.kt", TOTALS.replace("orders", "rows").replace("10", "5"))
    write_source(root, "Max.kt", TOTALS.replace("sumOf", "maxOf"))
    write_source(root, "Short.kt", SHORT)
    write_source(root, "ShortCopy.kt", SHORT.replace("(a", "(n").replace(", a", ", n"))


def test_given_a_renamed_copy_when_doppel_runs_then_one_group_lists_it_with_its_score(tmp_path, capsys, monkeypatch):
    shutil.copytree(FIXTURES / "renamed", tmp_path / "renamed")
    monkeypatch.chdir(tmp_path)

    assert run(["renamed"]) == 0

    assert capsys.readouterr().out == (
        "renamed/Left.kt:4-8 totals\n"
        "  1.00  renamed/Right.kt:4-8  sums\n"
    )


def test_given_each_threshold_option_when_doppel_runs_then_the_groups_change(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    monkeypatch.chdir(tmp_path)

    def listed(*args: str) -> list[tuple[str, list[str]]]:
        assert run(list(args)) == 0
        return listed_groups(capsys.readouterr().out)

    assert listed() == [("Orders.kt", ["Report.kt"])]
    assert listed("--threshold", "0.7") == [("Max.kt", ["Orders.kt", "Report.kt"]), ("Orders.kt", ["Report.kt"])]
    assert listed("--min-lines", "3") == [("Orders.kt", ["Report.kt"]), ("Short.kt", ["ShortCopy.kt"])]
    assert listed("--min-nodes", "200") == []


def test_given_paths_and_fragments_when_doppel_runs_then_only_those_files_are_compared(tmp_path, capsys, monkeypatch):
    for name in ["orders/OrderA.kt", "orders/OrderB.kt", "users/UserCopy.kt"]:
        write_source(tmp_path, name, TOTALS)
    monkeypatch.chdir(tmp_path)

    assert run(["orders"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("orders/OrderA.kt", ["orders/OrderB.kt"])]

    assert run(["orders/OrderA.kt", "users"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("orders/OrderA.kt", ["users/UserCopy.kt"])]

    assert run(["User", "OrderB"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("orders/OrderB.kt", ["users/UserCopy.kt"])]


def test_given_a_fragment_naming_a_folder_above_the_root_when_doppel_runs_then_nothing_is_compared(tmp_path, capsys, monkeypatch):
    project(tmp_path / "app")
    monkeypatch.chdir(tmp_path / "app")

    assert run([tmp_path.name]) == 0
    assert capsys.readouterr().out == "No source files to analyze.\n"


def test_given_a_skipped_test_file_when_named_then_it_is_compared(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "src/main/kotlin/Orders.kt", TOTALS)
    write_source(tmp_path, "src/test/kotlin/OrdersTest.kt", TOTALS)
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0
    assert listed_groups(capsys.readouterr().out) == []

    assert run(["src/main", "src/test/kotlin/OrdersTest.kt"]) == 0
    assert listed_groups(capsys.readouterr().out) == [
        ("src/main/kotlin/Orders.kt", ["src/test/kotlin/OrdersTest.kt"])
    ]


def test_given_a_bad_option_when_doppel_runs_then_it_exits_1_with_the_reason(capsys):
    for args, reason in [
        (["--threshold", "high"], "--threshold requires a number"),
        (["--threshold", "nan"], "--threshold requires a number from 0 to 1"),
        (["--threshold", "inf"], "--threshold requires a number from 0 to 1"),
        (["--threshold", "1.5"], "--threshold requires a number from 0 to 1"),
        (["--min-lines", "-2"], "--min-lines requires a value"),
        (["--min-nodes", "2.5"], "--min-nodes requires an integer"),
        (["--min-lines"], "--min-lines requires a value"),
        (["--verbose"], "Unknown option: --verbose"),
    ]:
        assert run(args) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert reason in captured.err


def test_given_a_broken_file_when_doppel_runs_then_it_is_named_counted_and_other_copies_are_listed(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "Orders.kt", TOTALS)
    write_source(tmp_path, "Report.kt", TOTALS)
    write_source(tmp_path, "Broken.kt", "fun broken( {\n    val x =\n}\n")
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0

    captured = capsys.readouterr()
    assert listed_groups(captured.out) == [("Orders.kt", ["Report.kt"])]
    err = captured.err.splitlines()
    assert err[0] == "doppel: Broken.kt has parse errors; compared as parsed"
    assert re.fullmatch(
        r"doppel: 3 files scanned, 2 functions compared, 1 file with parse errors, \d+\.\d\ds",
        err[-1],
    )
    assert len(err) == 2


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file chmod 000 denies")
@pytest.mark.parametrize(
    ("args", "heading", "copy"),
    [
        ([], "Orders.kt", "Report.kt"),
        (["--changed"], "Report.kt", "Orders.kt"),
        (["--changed-functions"], "Report.kt", "Orders.kt"),
        (["--focus", "Report.kt", "Locked.kt"], "Report.kt", "Orders.kt"),
    ],
)
def test_given_an_unreadable_file_when_doppel_runs_then_it_is_skipped_with_a_warning_and_other_copies_are_listed(args, heading, copy, tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "Orders.kt", TOTALS)
    write_source(tmp_path, "Report.kt", TOTALS)
    commit_all(tmp_path)
    write_source(tmp_path, "Report.kt", TOTALS.replace("orders", "rows"))
    write_source(tmp_path, "Locked.kt", TOTALS)
    (tmp_path / "Locked.kt").chmod(0)
    monkeypatch.chdir(tmp_path)

    assert run(args) == 0

    captured = capsys.readouterr()
    assert listed_groups(captured.out) == [(heading, [copy])]
    err = captured.err.splitlines()
    assert err[0] == "doppel: Locked.kt cannot be read; skipped"
    assert re.fullmatch(r"doppel: 2 files scanned, 2 functions compared, 0 files with parse errors, \d+\.\d\ds", err[-1])


def test_given_a_skipped_test_folder_when_named_then_it_is_compared(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "src/main/kotlin/Orders.kt", TOTALS)
    write_source(tmp_path, "src/test/kotlin/OrdersCopy.kt", TOTALS)
    write_source(tmp_path, "src/test/kotlin/ReportCopy.kt", TOTALS)
    monkeypatch.chdir(tmp_path)

    assert run(["src"]) == 0
    assert listed_groups(capsys.readouterr().out) == []

    assert run(["src/test"]) == 0
    assert listed_groups(capsys.readouterr().out) == [
        ("src/test/kotlin/OrdersCopy.kt", ["src/test/kotlin/ReportCopy.kt"])
    ]


def test_given_pairs_when_doppel_runs_then_they_are_printed_and_no_file_is_written(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert run(["--threshold", "0.7"]) == 0

    assert len(listed_groups(capsys.readouterr().out)) == 2
    assert not (tmp_path / ".doppel").exists()

    assert run(["--min-nodes", "200"]) == 0

    assert capsys.readouterr().out == "No duplicate candidates found.\n"
    assert not (tmp_path / ".doppel").exists()


def test_when_help_runs_then_it_names_no_file_and_exit_code_0_is_the_run_having_finished(capsys):
    assert run(["--help"]) == 0

    out = capsys.readouterr().out
    assert "json" not in out.lower()
    assert ".doppel" not in out
    assert "  0  the run finished\n" in out


def test_when_help_runs_then_a_heading_and_each_copy_line_end_with_the_function_name(capsys):
    assert run(["--help"]) == 0

    text = " ".join(capsys.readouterr().out.split())
    assert "Each function that has a copy heads a group: its location and name" in text
    assert "then one line per copy with the score, the copy's location and its name" in text


def test_given_a_new_copy_of_committed_code_when_doppel_runs_with_changed_then_only_its_group_is_listed(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "committed")
    write_source(tmp_path, "MaxCopy.kt", TOTALS.replace("sumOf", "maxOf").replace("orders", "items"))
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0
    assert ("Orders.kt", ["Report.kt"]) in listed_groups(capsys.readouterr().out)

    assert run(["--changed"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("MaxCopy.kt", ["Max.kt"])]


def test_given_no_git_repository_when_doppel_runs_with_changed_then_it_exits_1(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    assert run(["--changed"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not a git repository" in captured.err


def test_given_a_change_above_the_current_directory_when_doppel_runs_with_changed_on_it_then_its_group_is_listed(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "committed")
    write_source(tmp_path, "Report.kt", TOTALS.replace("orders", "lines"))
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")

    assert run(["--changed", ".."]) == 0
    above = tmp_path.resolve().as_posix()
    assert listed_groups(capsys.readouterr().out) == [(f"{above}/Report.kt", [f"{above}/Orders.kt"])]


def test_given_another_repository_when_doppel_runs_with_changed_on_it_then_git_is_asked_there(tmp_path, capsys, monkeypatch):
    repo = tmp_path / "repo"
    project(repo)
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "committed")
    write_source(repo, "Report.kt", TOTALS.replace("orders", "lines"))
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    assert run(["--changed", "../repo"]) == 0
    named = repo.resolve().as_posix()
    assert listed_groups(capsys.readouterr().out) == [(f"{named}/Report.kt", [f"{named}/Orders.kt"])]


SHORT_EDITED = SHORT.replace("fun short(a: Int): Int {", "fun short(a: Int): Int {\n    val b = a + 1")
PAIRED = TOTALS + "\n" + SHORT_EDITED


def paired_project(root: Path) -> None:
    """`Paired.kt` holds `totals` (lines 1-5) and `short` (lines 7-10), each copied in another file."""

    write_source(root, "Paired.kt", PAIRED)
    write_source(root, "Totals.kt", TOTALS)
    write_source(root, "Short.kt", SHORT_EDITED)


def test_given_one_of_two_copied_functions_edited_when_doppel_runs_with_changed_functions_then_only_its_group_is_listed(tmp_path, capsys, monkeypatch):
    paired_project(tmp_path)
    commit_all(tmp_path)
    write_source(tmp_path, "Paired.kt", PAIRED.replace("+ 10", "+ 11"))
    monkeypatch.chdir(tmp_path)

    assert run(["--min-lines", "3", "--changed"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("Paired.kt", ["Totals.kt"]), ("Paired.kt", ["Short.kt"])]

    assert run(["--min-lines", "3", "--changed-functions"]) == 0
    assert capsys.readouterr().out == "Paired.kt:1-5 totals\n  1.00  Totals.kt:1-5  totals\n"


def test_given_a_new_untracked_copy_when_doppel_runs_with_changed_functions_then_it_heads_its_group(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    commit_all(tmp_path)
    write_source(tmp_path, "MaxCopy.kt", TOTALS.replace("sumOf", "maxOf").replace("orders", "items"))
    monkeypatch.chdir(tmp_path)

    assert run(["--changed-functions"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("MaxCopy.kt", ["Max.kt"])]


@pytest.mark.parametrize("option", ["--changed", "--changed-functions"])
def test_given_committed_pairs_and_no_uncommitted_change_when_doppel_runs_with_a_git_focus_then_only_the_no_candidates_line_is_printed(option, tmp_path, capsys, monkeypatch):
    # The focus is empty, not absent: the copies a run with no focus lists stay unlisted.
    project(tmp_path)
    commit_all(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert run([option]) == 0
    assert capsys.readouterr().out == "No duplicate candidates found.\n"


def test_given_an_edit_outside_every_function_when_doppel_runs_with_changed_functions_then_nothing_is_listed(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    commit_all(tmp_path)
    write_source(tmp_path, "Orders.kt", "// Totals per customer.\n\n" + TOTALS + "\nval limit = 3\n")
    monkeypatch.chdir(tmp_path)

    assert run(["--changed"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("Orders.kt", ["Report.kt"])]

    assert run(["--changed-functions"]) == 0
    assert capsys.readouterr().out == "No duplicate candidates found.\n"


STAND_IN_SPEC = """\
from dataclasses import replace

from doppel.languages.kotlin import SPEC as KOTLIN

SPEC = replace(KOTLIN, name="standin", extensions=frozenset({".si", ".sin"}))
"""


def test_given_an_extra_spec_file_when_help_runs_then_it_is_listed_with_its_extensions(tmp_path, capsys, monkeypatch):
    import doppel.languages
    from doppel.discover import specs

    (tmp_path / "standin.py").write_text(STAND_IN_SPEC, encoding="utf-8")
    monkeypatch.setattr(doppel.languages, "__path__", [*doppel.languages.__path__, str(tmp_path)])
    monkeypatch.delitem(sys.modules, "doppel.languages.standin", raising=False)
    specs.cache_clear()
    try:
        assert run(["--help"]) == 0
    finally:
        specs.cache_clear()

    [languages] = [line for line in capsys.readouterr().out.splitlines() if line.startswith("Languages: ")]
    assert "Standin (.si .sin)" in languages


def test_given_an_edit_above_the_current_directory_when_doppel_runs_with_changed_functions_on_it_then_its_group_is_listed(tmp_path, capsys, monkeypatch):
    paired_project(tmp_path)
    commit_all(tmp_path)
    write_source(tmp_path, "Paired.kt", PAIRED.replace("+ 10", "+ 11"))
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")

    assert run(["--min-lines", "3", "--changed-functions", ".."]) == 0
    above = tmp_path.resolve().as_posix()
    assert listed_groups(capsys.readouterr().out) == [(f"{above}/Paired.kt", [f"{above}/Totals.kt"])]


def test_given_another_repository_when_doppel_runs_with_changed_functions_on_it_then_git_is_asked_there(tmp_path, capsys, monkeypatch):
    repo = tmp_path / "repo"
    paired_project(repo)
    commit_all(repo)
    write_source(repo, "Paired.kt", PAIRED.replace("+ 10", "+ 11"))
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    assert run(["--min-lines", "3", "--changed-functions", "../repo"]) == 0
    named = repo.resolve().as_posix()
    assert listed_groups(capsys.readouterr().out) == [(f"{named}/Paired.kt", [f"{named}/Totals.kt"])]


@pytest.mark.parametrize("name", ["Paired Copy.kt", "Café.kt", "日本.kt", 'Qu"o\\te.kt'])
def test_given_an_unusual_file_name_when_doppel_runs_with_changed_functions_then_the_edited_function_heads_its_group_under_its_real_name(name, tmp_path, capsys, monkeypatch):
    paired_project(tmp_path)
    (tmp_path / "Paired.kt").rename(tmp_path / name)
    commit_all(tmp_path)
    write_source(tmp_path, name, PAIRED.replace("+ 10", "+ 11"))
    monkeypatch.chdir(tmp_path)

    assert run(["--min-lines", "3", "--changed-functions"]) == 0
    assert capsys.readouterr().out == f"{name}:1-5 totals\n  1.00  Totals.kt:1-5  totals\n"


@pytest.mark.parametrize("setting", ["diff.noprefix", "diff.mnemonicPrefix"])
def test_given_git_settings_rewriting_diff_paths_when_doppel_runs_with_changed_functions_then_the_report_is_unchanged(tmp_path, capsys, monkeypatch, setting):
    # Under a top-level `b/` folder, a path read without doppel's own prefixes loses its folder.
    write_source(tmp_path, "b/Paired.kt", PAIRED)
    write_source(tmp_path, "Totals.kt", TOTALS)
    write_source(tmp_path, "Short.kt", SHORT_EDITED)
    commit_all(tmp_path)
    write_source(tmp_path, "b/Paired.kt", PAIRED.replace("+ 10", "+ 11"))
    git(tmp_path, "config", setting, "true")
    monkeypatch.chdir(tmp_path)

    assert run(["--min-lines", "3", "--changed-functions"]) == 0
    assert capsys.readouterr().out == "b/Paired.kt:1-5 totals\n  1.00  Totals.kt:1-5  totals\n"


def test_given_no_git_repository_when_doppel_runs_with_changed_functions_then_it_exits_1_naming_the_option(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    assert run(["--changed-functions"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("doppel: --changed-functions needs git: ")
    assert "not a git repository" in captured.err


def test_given_a_function_copied_from_another_file_when_doppel_runs_with_focus_on_it_then_only_its_group_is_listed(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "A.kt", TOTALS)
    write_source(tmp_path, "C.kt", TOTALS.replace("orders", "rows"))
    write_source(tmp_path, "B.kt", TOTALS.replace("sumOf", "maxOf"))
    write_source(tmp_path, "D.kt", TOTALS.replace("sumOf", "maxOf").replace("orders", "rows"))
    commit_all(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert run(["A.kt"]) == 0
    assert capsys.readouterr().out == "No duplicate candidates found.\n"

    assert run(["--focus", "A.kt"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("A.kt", ["C.kt"])]


def test_given_a_test_file_when_doppel_runs_with_focus_on_it_then_it_heads_a_group_with_production_code(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "src/main/kotlin/Orders.kt", TOTALS)
    write_source(tmp_path, "src/test/kotlin/OrdersTest.kt", TOTALS)
    monkeypatch.chdir(tmp_path)

    assert run(["--focus", "src/test/kotlin/OrdersTest.kt"]) == 0
    assert listed_groups(capsys.readouterr().out) == [
        ("src/test/kotlin/OrdersTest.kt", ["src/main/kotlin/Orders.kt"])
    ]


def test_given_a_deleted_file_and_a_readme_named_beside_a_source_file_when_doppel_runs_with_focus_then_each_is_skipped_and_the_source_groups_are_listed(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "A.kt", TOTALS)
    write_source(tmp_path, "C.kt", TOTALS.replace("orders", "rows"))
    write_source(tmp_path, "README.md", "# Orders\n")
    monkeypatch.chdir(tmp_path)

    assert run(["--focus", "Gone.kt", "README.md", "A.kt"]) == 0

    captured = capsys.readouterr()
    assert listed_groups(captured.out) == [("A.kt", ["C.kt"])]
    err = captured.err.splitlines()
    assert err[:2] == [
        "doppel: Gone.kt does not exist; skipped",
        "doppel: README.md is not a source file doppel reads; skipped",
    ]
    assert len(err) == 3


def test_given_focus_with_no_path_when_doppel_runs_then_it_exits_1_with_the_reason(capsys):
    assert run(["--focus"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("--focus requires a path\n")


def test_given_focus_on_no_source_file_when_doppel_runs_then_it_exits_1_with_the_reason(tmp_path, capsys, monkeypatch):
    project(tmp_path)
    write_source(tmp_path, "README.md", "# Orders\n")
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(tmp_path)

    assert run(["--focus", "Gone.kt", "README.md", "docs"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "doppel: Gone.kt does not exist; skipped",
        "doppel: README.md is not a source file doppel reads; skipped",
        "doppel: docs holds no source file doppel compares; skipped",
        "doppel: --focus names no source file doppel reads",
    ]
    assert not (tmp_path / ".doppel").exists()


def test_given_focus_and_changed_functions_when_doppel_runs_then_the_groups_of_both_are_listed(tmp_path, capsys, monkeypatch):
    paired_project(tmp_path)
    write_source(tmp_path, "A.kt", TOTALS.replace("sumOf", "maxOf"))
    write_source(tmp_path, "C.kt", TOTALS.replace("sumOf", "maxOf").replace("orders", "rows"))
    commit_all(tmp_path)
    write_source(tmp_path, "Paired.kt", PAIRED.replace("+ 10", "+ 11"))
    monkeypatch.chdir(tmp_path)

    assert run(["--min-lines", "3", "--focus", "A.kt"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("A.kt", ["C.kt"])]

    assert run(["--min-lines", "3", "--changed-functions"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("Paired.kt", ["Totals.kt"])]

    assert run(["--min-lines", "3", "--focus", "A.kt", "--changed-functions"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("A.kt", ["C.kt"]), ("Paired.kt", ["Totals.kt"])]


def test_given_focus_and_changed_when_doppel_runs_then_the_groups_of_both_are_listed(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "Orders.kt", TOTALS)
    write_source(tmp_path, "Report.kt", TOTALS.replace("orders", "rows"))
    write_source(tmp_path, "A.kt", TOTALS.replace("sumOf", "maxOf"))
    write_source(tmp_path, "C.kt", TOTALS.replace("sumOf", "maxOf").replace("orders", "rows"))
    commit_all(tmp_path)
    write_source(tmp_path, "Report.kt", TOTALS.replace("orders", "lines"))
    monkeypatch.chdir(tmp_path)

    assert run(["--focus", "A.kt"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("A.kt", ["C.kt"])]

    assert run(["--changed"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("Report.kt", ["Orders.kt"])]

    assert run(["--focus", "A.kt", "--changed"]) == 0
    assert listed_groups(capsys.readouterr().out) == [("A.kt", ["C.kt"]), ("Report.kt", ["Orders.kt"])]


MAX = TOTALS.replace("sumOf", "maxOf")


def test_given_three_functions_that_all_resemble_each_other_when_doppel_runs_then_each_pair_is_listed_once_under_its_first_side(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "a/A.kt", TOTALS)
    write_source(tmp_path, "b/B.kt", TOTALS.replace("orders", "rows"))
    write_source(tmp_path, "c/C.kt", MAX)
    monkeypatch.chdir(tmp_path)

    assert run(["--threshold", "0.7"]) == 0

    assert capsys.readouterr().out == (
        "a/A.kt:1-5 totals\n"
        "  1.00  b/B.kt:1-5  totals\n"
        "  0.71  c/C.kt:1-5  totals\n"
        "\n"
        "b/B.kt:1-5 totals\n"
        "  0.71  c/C.kt:1-5  totals\n"
    )


def test_given_a_copy_of_an_earlier_function_when_doppel_runs_with_focus_on_the_later_file_then_the_later_function_is_the_heading(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "A.kt", TOTALS)
    write_source(tmp_path, "C.kt", TOTALS.replace("orders", "rows"))
    monkeypatch.chdir(tmp_path)

    assert run(["--focus", "C.kt"]) == 0

    assert capsys.readouterr().out == "C.kt:1-5 totals\n  1.00  A.kt:1-5  totals\n"


def test_given_two_uncommitted_functions_that_copy_each_other_when_doppel_runs_with_changed_functions_then_each_heads_a_group_with_the_other(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "README.md", "# Orders\n")
    commit_all(tmp_path)
    write_source(tmp_path, "New.kt", TOTALS)
    write_source(tmp_path, "NewCopy.kt", TOTALS.replace("orders", "rows"))
    monkeypatch.chdir(tmp_path)

    assert run(["--changed-functions"]) == 0

    assert capsys.readouterr().out == (
        "New.kt:1-5 totals\n"
        "  1.00  NewCopy.kt:1-5  totals\n"
        "\n"
        "NewCopy.kt:1-5 totals\n"
        "  1.00  New.kt:1-5  totals\n"
    )


def test_given_copied_functions_at_lines_20_and_100_of_one_file_when_doppel_runs_then_line_20_is_listed_first(tmp_path, capsys, monkeypatch):
    write_source(tmp_path, "F.kt", "\n" * 19 + TOTALS + "\n" * 75 + MAX)
    write_source(tmp_path, "G.kt", TOTALS)
    write_source(tmp_path, "H.kt", MAX)
    monkeypatch.chdir(tmp_path)

    assert run([]) == 0

    assert capsys.readouterr().out == (
        "F.kt:20-24 totals\n"
        "  1.00  G.kt:1-5  totals\n"
        "\n"
        "F.kt:100-104 totals\n"
        "  1.00  H.kt:1-5  totals\n"
    )


def test_given_a_scanned_folder_outside_the_current_directory_when_doppel_runs_then_its_groups_follow_scan_order(tmp_path, capsys, monkeypatch):
    # Its files print as absolute paths, which a sort of the printed text would put first.
    write_source(tmp_path, "app/X.kt", TOTALS)
    write_source(tmp_path, "app/XCopy.kt", TOTALS)
    write_source(tmp_path, "lib/Y.kt", MAX)
    write_source(tmp_path, "lib/YCopy.kt", MAX)
    monkeypatch.chdir(tmp_path / "app")

    assert run([".", "../lib"]) == 0

    lib = (tmp_path / "lib").resolve().as_posix()
    assert listed_groups(capsys.readouterr().out) == [("X.kt", ["XCopy.kt"]), (f"{lib}/Y.kt", [f"{lib}/YCopy.kt"])]


@pytest.fixture
def no_download(monkeypatch):
    """Every parser download fails, as with no network, and no parser is already loaded."""

    import tree_sitter_language_pack

    def fail(names):
        raise tree_sitter_language_pack.DownloadError("Download error: io: Connection refused (os error 61)")

    monkeypatch.setattr(tree_sitter_language_pack, "download", fail)
    parser_for.cache_clear()
    yield
    parser_for.cache_clear()


@pytest.mark.parametrize(
    ("name", "source", "language"),
    [("Orders.kt", TOTALS, "Kotlin"), ("Orders.fs", "let total orders = List.sum orders\n", "F#")],
)
def test_given_a_parser_that_cannot_be_downloaded_when_doppel_runs_then_it_names_the_language_and_the_reason_and_exits_1(name, source, language, no_download, tmp_path, capsys, monkeypatch):
    write_source(tmp_path, name, source)
    write_source(tmp_path, name.replace("Orders", "Copy"), source)
    monkeypatch.chdir(tmp_path)

    assert run([]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"doppel: the {language} parser cannot be loaded: Download error: io: Connection refused (os error 61)\n"
    )
