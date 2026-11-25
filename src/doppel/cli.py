# Adapted from dryer, https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/cli.py (0BSD).
"""Command line: `doppel [options] [path-or-fragment ...]` prints the functions that have a copy, grouped by function."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from doppel.changed import ChangedLines, GitStatusError, changed_files, changed_lines
from doppel.discover import iter_source_files, spec_of, specs
from doppel.model import Entry, Span
from doppel.report import format_text
from doppel.scan import LanguageUnavailable, display_path, find_duplicates, scan_files, span_of

HELP = """\
Usage: doppel [options] [path-or-fragment ...]

Find functions whose structure is similar. Each function is normalized (the
names of the functions called, operators and the shape of the code stay;
local names, literals and comments do not) and compared with the other
functions of the same language. The score is the Jaccard similarity of their
structural fingerprints.

Each function that has a copy heads a group: its location and name, then one
line per copy with the score, the copy's location and its name, closest
first. A name is printed as the source writes it; a function whose name is
not found shows its location alone. Groups follow scan order (files by path,
functions by line). With no focus, each pair is listed once, under whichever
function comes first. With --changed, --changed-functions or --focus, every
function in focus that has a copy heads a group listing all its copies.

Languages: {languages}.

Options:
  -h, --help      Print this help and exit.
  --changed       Compare the functions in files git reports as added,
                  modified or untracked against every function scanned.
  --changed-functions
                  Compare the functions holding a line changed since the
                  last commit (git diff HEAD), and every function of an
                  untracked file, against every function scanned.
  --focus         Scan the current directory and compare the functions in
                  the files the path arguments name against every function
                  scanned. A named file is compared even when it is test
                  code; a named folder is walked with the usual skips. A
                  path that is missing or holds no source file is skipped
                  with a line on standard error.
  --threshold N   Minimum similarity score, 0 to 1, default 0.82.
  --min-lines N   Minimum source lines in a function, default 4.
  --min-nodes N   Minimum normalized syntax nodes, default 20.

Arguments:
  path            File or folder to scan instead of the current directory.
                  Test code is compared when its path is named.
  fragment        Any other argument: only files whose path contains it are
                  compared. With --focus, every argument is a path.

Exit codes:
  0  the run finished
  1  usage error (--focus with no path is one), git failing for --changed
     or --changed-functions (outside a git repository, or a committed
     source file doppel cannot read under --changed-functions), --focus
     naming no source file doppel reads, or a language's parser that cannot
     be loaded (its first download needs the network)
"""


def _shown(language: str) -> str:
    return language.capitalize()


def help_text() -> str:
    languages = ", ".join(
        f"{_shown(spec.name)} ({' '.join(sorted(spec.extensions))})" for spec in specs()
    )
    return HELP.format(languages=languages)


@dataclass
class Options:
    positionals: list[str] = field(default_factory=list)
    help: bool = False
    changed: bool = False
    changed_functions: bool = False
    focus: bool = False
    # dryer's defaults.
    threshold: float = 0.82
    min_lines: int = 4
    min_nodes: int = 20


def _take(args: list[str], index: int, option: str) -> str:
    if index + 1 >= len(args) or not args[index + 1] or args[index + 1].startswith("-"):
        raise ValueError(f"{option} requires a value")
    return args[index + 1]


def _number(value: str, option: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{option} requires a number") from exc


def _score(value: str, option: str) -> float:
    parsed = _number(value, option)
    if not 0 <= parsed <= 1:
        raise ValueError(f"{option} requires a number from 0 to 1")
    return parsed


def _count(value: str, option: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{option} requires an integer") from exc
    if parsed < 0:
        raise ValueError(f"{option} requires a non-negative integer")
    return parsed


def parse_args(args: list[str]) -> Options:
    """The options in `args`. Raises ValueError naming what is wrong."""

    if any(arg in {"-h", "--help"} for arg in args):
        return Options(help=True)
    options = Options()
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--threshold":
            options.threshold = _score(_take(args, index, arg), arg)
        elif arg == "--min-lines":
            options.min_lines = _count(_take(args, index, arg), arg)
        elif arg == "--min-nodes":
            options.min_nodes = _count(_take(args, index, arg), arg)
        elif arg == "--changed":
            options.changed = True
            index += 1
            continue
        elif arg == "--changed-functions":
            options.changed_functions = True
            index += 1
            continue
        elif arg == "--focus":
            options.focus = True
            index += 1
            continue
        elif arg.startswith("-"):
            raise ValueError(f"Unknown option: {arg}")
        else:
            options.positionals.append(arg)
            index += 1
            continue
        index += 2
    if options.focus and not options.positionals:
        raise ValueError("--focus requires a path")
    return options


def _positionals(root: Path, args: list[str]) -> tuple[list[Path], list[str]]:
    """Arguments naming an existing path, and the rest, which are fragments."""

    existing: list[Path] = []
    fragments: list[str] = []
    for arg in args:
        path = Path(arg)
        if not path.is_absolute():
            path = root / arg
        if path.exists():
            existing.append(path.resolve())
        else:
            fragments.append(arg)
    return existing, fragments


def _explicit_files(existing: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in existing:
        if path.is_dir():
            files.extend(iter_source_files(path))
        elif spec_of(path) is not None:
            files.append(path)
    return files


def select_files(root: Path, existing: list[Path], fragments: list[str]) -> list[Path]:
    """Files under the `existing` paths, or under `root` when none is named.

    A fragment keeps only the files whose displayed path contains it.
    """

    files = _explicit_files(existing) if existing else iter_source_files(root)
    if fragments:
        files = [
            path for path in files if any(item in display_path(path, root) for item in fragments)
        ]
    return sorted(set(files), key=lambda path: path.as_posix())


class _Stop(Exception):
    """A reason doppel exits 1, printed on standard error."""


def _named_files(root: Path, args: list[str]) -> list[Path]:
    """The source files the `--focus` arguments name.

    A path that is missing or holds no source file is skipped with a warning.
    """

    files: list[Path] = []
    for arg in args:
        path = root / arg
        if not path.exists():
            print(f"doppel: {arg} does not exist; skipped", file=sys.stderr)
            continue
        found = _explicit_files([path.resolve()])
        if not found:
            what = "holds no source file doppel compares" if path.is_dir() else "is not a source file doppel reads"
            print(f"doppel: {arg} {what}; skipped", file=sys.stderr)
        files.extend(found)
    if not files:
        raise _Stop("doppel: --focus names no source file doppel reads")
    return files


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _git_folders(root: Path, searched: list[Path]) -> set[Path]:
    """Where git is asked: where the scanned files are, in each named folder,
    or a named file's folder, or in `root` when no path is named."""

    return {path if path.is_dir() else path.parent for path in searched} or {root}


def _changed_paths(root: Path, searched: list[Path], files: list[Path]) -> frozenset[str]:
    """The display paths of the selected files git reports as changed."""

    changed = set().union(*(changed_files(folder) for folder in _git_folders(root, searched)))
    return frozenset(display_path(path, root) for path in files if path in changed)


def _changed_lines(root: Path, searched: list[Path]) -> ChangedLines:
    """The changed lines of every repository holding a git folder.

    Folders in one repository give the same answer, so a later one only adds
    files from another repository.
    """

    changes: ChangedLines = {}
    for folder in _git_folders(root, searched):
        for path, lines in changed_lines(folder).items():
            changes.setdefault(path, lines)
    return changes


def _asking_git[T](option: str, needs: str, ask: Callable[[], T]) -> T:
    try:
        return ask()
    except GitStatusError as exc:
        raise _Stop(f"doppel: {option} needs {needs}: {exc}") from exc


def _select(
    root: Path, options: Options
) -> tuple[list[Path], frozenset[str] | None, ChangedLines | None]:
    """The files to scan, the display paths of the files in focus, and the
    lines changed since the last commit when `--changed-functions` asks.

    The focus is the named files with `--focus`, joined by the files git
    reports with `--changed`; None when neither option is given.
    """

    if options.focus:
        named = _named_files(root, options.positionals)
        files = sorted(set(iter_source_files(root)) | set(named), key=lambda path: path.as_posix())
        searched = [root, *named]
        focus_files = frozenset(display_path(path, root) for path in named)
    else:
        searched, fragments = _positionals(root, options.positionals)
        files = select_files(root, searched, fragments)
        focus_files = None
    if options.changed:
        changed = _asking_git("--changed", "git status", lambda: _changed_paths(root, searched, files))
        focus_files = (focus_files or frozenset()) | changed
    changes = None
    if options.changed_functions:
        changes = _asking_git("--changed-functions", "git", lambda: _changed_lines(root, searched))
    return files, focus_files, changes


def _in_files(entries: list[Entry], paths: frozenset[str]) -> frozenset[Span]:
    return frozenset(span_of(entry) for entry in entries if entry.file in paths)


def _touched(entries: list[Entry], root: Path, changes: ChangedLines) -> frozenset[Span]:
    """The entries whose line range holds a changed line."""

    by_file = {display_path(path, root): lines for path, lines in changes.items()}
    return frozenset(
        span_of(entry)
        for entry in entries
        if entry.file in by_file
        and (
            (lines := by_file[entry.file]) is None
            or any(entry.start_line <= line <= entry.end_line for line in lines)
        )
    )


def run(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    try:
        options = parse_args(list(sys.argv[1:] if argv is None else argv))
    except ValueError as exc:
        print(f"{exc}\n\n{help_text()}", file=sys.stderr, end="")
        return 1
    if options.help:
        print(help_text(), end="")
        return 0
    root = Path.cwd()
    try:
        files, focus_files, changes = _select(root, options)
    except _Stop as exc:
        print(exc, file=sys.stderr)
        return 1
    if not files:
        print("No source files to analyze.")
        entries, broken, unreadable = [], [], []
    else:
        try:
            entries, broken, unreadable = scan_files(files, root, options.min_lines, options.min_nodes)
        except LanguageUnavailable as exc:
            print(f"doppel: the {_shown(exc.language)} parser cannot be loaded: {exc.reason}", file=sys.stderr)
            return 1
        for file in unreadable:
            print(f"doppel: {file} cannot be read; skipped", file=sys.stderr)
        for file in broken:
            print(f"doppel: {file} has parse errors; compared as parsed", file=sys.stderr)
        focus = None if focus_files is None else _in_files(entries, focus_files)
        if changes is not None:
            focus = (focus or frozenset()) | _touched(entries, root, changes)
        duplicates = find_duplicates(entries, options.threshold, focus)
        print(format_text(duplicates, [span_of(entry) for entry in entries], focus), end="")
    print(
        f"doppel: {_counted(len(files) - len(unreadable), 'file')} scanned, "
        f"{_counted(len(entries), 'function')} compared, "
        f"{_counted(len(broken), 'file')} with parse errors, "
        f"{time.perf_counter() - started:.2f}s",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> None:
    sys.exit(run(argv))
