# doppel

A command-line tool that finds functions whose structure is similar, Kotlin first. Python, parsed with tree-sitter through `tree-sitter-language-pack`, managed with uv.

## Commands

- Install: `uv sync` (needs network; the language pack downloads each parser on first use, so the first run needs network too).
- Test: `uv run pytest`
- Run: `uv run doppel [path]` (path defaults to the current directory).

## Rules

- The README changes with behavior: a change to what doppel reports, its options or its output updates the README in the same change.
- The engine (`src/doppel/*.py`) names no language. Everything about one language lives in its spec, `src/doppel/languages/<language>.py`, and its tests.
- `tree-sitter-language-pack` is pinned to an exact version in `pyproject.toml` and `uv.lock`: an upgrade can rename grammar nodes and silently change scores, so upgrade it on purpose and rerun the tests.
- Files copied or adapted from dryer keep their first-line comment naming the dryer file they came from.
- Code uses short, meaningful names. A comment that repeats what a name already says is removed; comments stay where they say why, record a grammar quirk, or name the dryer file the code came from.
