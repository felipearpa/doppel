import subprocess
from pathlib import Path

from doppel.discover import spec_of
from doppel.extract import entries_in_source
from doppel.model import Entry


def write_source(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def entries_of(source: str, name: str) -> list[Entry]:
    path = Path(name)
    entries, _has_error = entries_in_source(spec_of(path), source, path, name)
    return entries


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=doppel", "-c", "user.email=doppel@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def commit_all(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "committed")
