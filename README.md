# doppel

doppel finds functions whose structure is similar and scores how close each pair is. It reads Kotlin (`.kt`) and Swift (`.swift`); `doppel --help` lists the languages it knows.

Each function is normalized: the names of the functions called, the operators and the shape of the code stay, while local names, literals and comments do not. The score of a pair is the share of structural fingerprints the two functions have in common (Jaccard similarity), from 0 to 1. Functions are compared only with functions of the same language. Five copies of one function make ten pairs, and with no focus each pair is listed once, so they take four groups.

## Install

```bash
uv sync
```

The first run in each language downloads that language's parser, so it needs network.

## Usage

```bash
uv run doppel [options] [path-or-fragment ...]
```

Prints one group per function that has a copy: the function's location (`file:start-end`, relative to the current directory) and name, then one indented line per copy with its score, location and name, closest first; copies with the same score, and the groups themselves, follow scan order (files by path, then functions by line). `uv run doppel tests/fixtures/renamed` prints:

```
tests/fixtures/renamed/Left.kt:4-8 totals
  1.00  tests/fixtures/renamed/Right.kt:4-8  sums
```

The name is the function's own, without its class or extension receiver (the path says where it is), printed as the source writes it: an operator keeps its symbol (`==`), and a name written between backticks keeps them (`` `returns total when paid` ``). A function whose name doppel cannot find is printed as its location alone, with nothing after it. Two functions can share a name (overloads, or `equals` in two classes), so a function is identified by its location, never by its name alone.

Which functions head a group depends on the focus. With no focus (no `--changed`, `--changed-functions` or `--focus`), each pair is listed once, under whichever of its two functions comes first in scan order, so a function's copies are split between its own group and the groups of earlier functions, and the last of three mutual copies heads no group. Run with `--threshold 0.7`, since the third function scores 0.71 against the other two:

```
a/A.kt:1-5 totals
  1.00  b/B.kt:1-5  totals
  0.71  c/C.kt:1-5  totals

b/B.kt:1-5 totals
  0.71  c/C.kt:1-5  totals
```

With a focus, every function in focus that has a copy heads a group listing all its copies, wherever they are, so each group is complete on its own, and a pair of two functions in focus is listed twice, once under each. A run where nothing is in focus, `--changed` with a clean tree for instance, lists nothing; it never falls back to the no-focus layout. When nothing is listed, doppel prints `No duplicate candidates found.`

With no argument, the current directory is scanned. An argument that names an existing file or folder is scanned instead. Any other argument is a fragment: only files whose path as listed in the report contains it are compared, so a fragment naming a folder above the current directory matches nothing. A path that does not exist is read as a fragment too: a misspelled path usually matches nothing, and doppel prints `No source files to analyze.` and still exits 0.

Examples, run from this repository:

```bash
uv run doppel                                         # scan the current directory
uv run doppel tests/fixtures/renamed                  # scan one folder
uv run doppel tests/fixtures/swift-renamed            # the same, in Swift
uv run doppel --threshold 0.9 --min-lines 5           # closer copies, longer functions
uv run doppel tests renamed                           # scan tests, only paths containing "renamed"
uv run doppel --changed                               # the copies of functions in files git reports as changed
uv run doppel --changed-functions                     # the copies of functions changed since the last commit
uv run doppel --focus tests/fixtures/renamed/Left.kt  # the copies of functions in Left.kt, in the whole directory
uv run doppel --help
```

Options:

- `--threshold N`: minimum similarity score for a copy to be listed, from 0 to 1, default 0.82.
- `--min-lines N`: minimum source lines in a function, default 4.
- `--min-nodes N`: minimum normalized syntax nodes in a function, default 20.
- `--changed`: the functions in focus are those in a file git reports as added, modified or untracked (`git status`); each that has a copy heads a group with all its copies. A copy can be any function scanned, so a new copy of code already committed is found, while two unchanged functions copying each other are not listed. Every selected file is still parsed. Run outside a git repository, it prints git's reason and exits 1.
- `--changed-functions`: the functions in focus are those an uncommitted change touched, each compared, as with `--changed`, against every function scanned. A function is touched when a line in its range changed since the last commit (`git diff HEAD`, staged or not), and every function of an untracked file is touched; before the first commit, every function of each file `git status` reports is. A function's range runs from its first annotation (`@Deprecated`, `@discardableResult`) to its closing brace, so editing only an annotation touches it, while a doc comment or other comment above the function lies outside the range and editing only it touches nothing. Deleting lines touches only the line just above them (or line 1, for a deletion at the top of a file), so the function above a deletion counts only when that line is its last line: deleting a comment separated from the function by a blank line touches nothing. An edit outside every compared function, or inside code doppel does not compare (a Swift `init` or computed property, a function shorter than `--min-lines` or `--min-nodes`), touches nothing; an edit inside a nested function or lambda touches the function around it. A copy that existed before the change is listed when the change touches either function, under the touched one. As with `--changed`, git is asked where the scanned files are: in each named folder or named file's folder, or in the current directory when no path is named, so a folder above the current directory or in another repository works. Run outside a git repository, it prints git's reason and exits 1. With `--changed` too, the functions in focus of both head groups.
- `--focus`: the path arguments name the files to report on, and the current directory is scanned: the functions in focus are those in a named file, their copies being any function scanned, so a function copied from a file that was not named is found. Every argument is a path, never a fragment, and at least one is required. A named file is also scanned, so a test file named this way is compared; a named folder is walked with the usual skips (see What is skipped), so its test files are left out unless named themselves. A named path that does not exist (`doppel: Gone.kt does not exist; skipped`), a file doppel does not read (`doppel: README.md is not a source file doppel reads; skipped`) or a folder holding none (`doppel: docs holds no source file doppel compares; skipped`) is named on standard error and skipped, and the run goes on with the rest. When no named path is a source file doppel reads, doppel prints `doppel: --focus names no source file doppel reads` and exits 1, printing nothing on standard output. A named file whose functions are all shorter than `--min-lines` or `--min-nodes` lists nothing and exits 0. With `--changed` or `--changed-functions` too, the functions in focus of each head groups, and git is asked in the current directory and in each named file's folder. So the list of files a change touched, deleted files and READMEs included, can be passed as it is.
- `-h`, `--help`: print the help, with each language and its file extensions, and exit 0.

A bad option prints the reason and the help on standard error and exits 1, and so does `--focus` with no path argument. When git fails for `--changed` or `--changed-functions` (outside a git repository, or, under `--changed-functions`, on a committed source file doppel cannot read), doppel prints git's reason after the option's name and exits 1, and `--focus` naming no source file doppel reads exits 1 as well; otherwise doppel exits 0.

### Reading the report from an agent

A project whose agents run doppel can paste this paragraph into its `AGENTS.md`:

> doppel prints one group per function that has a copy: a heading with the function's location (`file:start-end`) and name, then one line per copy with its score, location and name, closest first. With `--changed`, `--changed-functions` or `--focus`, each function in focus that has a copy heads its own group, and that group lists all of its copies. With no focus, each pair is printed once, under whichever function comes first, so a function's copies are split between its own group and the groups of the functions before it; read the whole report before saying a function has no copy. Cite a function by its location, not by its name: two functions can share a name. `No duplicate candidates found.` means nothing was listed. doppel writes no file; a `.doppel` folder an earlier version left behind can be deleted.

### What is skipped

Folders `.git`, `.hg`, `.svn`, `.idea`, `.vscode` and `.doppel` are never scanned. For Kotlin, only `.kt` files are read (not `.kts` scripts), and these are skipped: `build` and `.gradle` folders above `src/` (a package folder called `build` inside `src/` is compared); any source set under `src/` whose name contains "test" (`test`, `androidTest`, `commonTest`, `testFixtures`); files ending in `Test.kt`, `Tests.kt` or `Spec.kt`. Scanning `src` still skips its test source sets, but a test file or test folder named as an argument (`src/test`) is compared; inside a named folder, files ending in `Test.kt`, `Tests.kt` or `Spec.kt` are still skipped unless they are named themselves. The scanned folder's own name never causes a skip: a project checked out in a folder called `build` is scanned. Run doppel from the module or project root, not from inside a source set: scanning `src/main` directly, a package folder called `build` is taken for build output and skipped.

For Swift, these are skipped at any depth: `.build`, `DerivedData`, `Pods` and `Carthage` folders (tool output and dependency checkouts); folders whose name ends in `Tests` (`Tests`, `AppTests`, `AppUITests`); files ending in `Tests.swift`. As for Kotlin, a test file or folder named as an argument (`Tests/AppTests`) is compared, though files ending in `Tests.swift` and folders ending in `Tests` inside a named folder are still skipped unless named themselves, and the scanned folder's own name never causes a skip.

A folder is left out of the walk only when every language skips it, so a Kotlin `build` folder is still walked for Swift files, and a Swift `.build` folder for Kotlin files; the files each language skips are still left out.

### Standard error

Each file the grammar cannot fully parse is named in a warning (`doppel: <file> has parse errors; compared as parsed`); the functions it could read are still compared. A source file doppel cannot open, for lack of permission for instance, is named on standard error (`doppel: <file> cannot be read; skipped`) and left out, and the run goes on with the other files. This holds whatever the options, with one exception: under `--changed-functions`, git cannot compare a committed file it cannot read, so doppel prints `doppel: --changed-functions needs git: ` followed by git's reason and exits 1. Each run ends with one summary line, whose count of files scanned leaves out the files that could not be read:

```
doppel: 42 files scanned, 310 functions compared, 1 file with parse errors, 0.84s
```

## What Kotlin compares

Local names, parameter and type names, a property that is only read, literals and comments do not count, and neither does swapping one modifier for another of its kind (`private` for `public`, `suspend` for `inline`, `val` for `var`). Adding or removing a modifier, or replacing it with one of another kind (`private` for `suspend`), does lower the score. These count:

- the name of the function called, in every call shape: `foo(x)`, `a.b.foo(x)`, `foo<T>(x)`, `foo { }` and infix calls such as `a shl b` or `0 until n`;
- the keywords and operators that change meaning: `return`, `break` and `continue`, labeled or not (`break@outer`), `throw`, `!!`, `?.`, `?:`, `::`, `as`, `as?`, `in`, `!in`, `is`, `!is`, `..`, `..<`, and the arithmetic, comparison, logical and assignment operators. The grammar gives `<` and `>` the same tokens as the brackets of type arguments, so those brackets count too (`listOf<Int>(a)` against `listOf(a)`);
- the code inside a string template: `"${foo(x)}"` and `"${bar(x)}"` differ, while plain string text does not count.

## What Swift compares

Functions declared with `func` and a body are compared; `init`, `deinit`, `subscript`, computed properties (SwiftUI `body` included) and property observers are not, and a function or closure inside a function stays part of it. As for Kotlin, local names, parameter and type names, a property that is only read, literals, comments, `let` against `var` and a swap of one modifier for another of its kind (`private` for `public`) do not count; adding a modifier, `async`, `throws` or `rethrows` does (swapping `throws` for `rethrows` does not: the grammar gives both one node type). These count:

- the name of the function called, in every call shape: `foo(x)`, `a.b.foo(x)`, `.foo(x)`, `foo { }`, and the type in a constructor call: `Set<Int>()`, `Foo.Bar()`, `[Int]()`, `[String: Int]()` (the key type);
- the keywords and operators that change meaning: `return`, `break` and `continue`, labeled or not, `throw`, `try`, `try?`, `try!`, `await`, `as`, `as?`, `as!`, `is`, `?.`, `!`, `??`, `&`, `...`, `..<`, and the arithmetic, comparison, logical and assignment operators. The grammar reads `!=`, `<=`, `>=` and operators a project defines as custom operators, so they count as the function they call. The grammar gives `<` and `>` the same tokens as the brackets of type arguments, so those brackets count too (`Set<Int>(a)` against `Set(a)`);
- the code inside a string interpolation, raw strings included: `"\(foo(x))"` and `"\(bar(x))"` differ, while plain string text does not count.

## Adding a language

A language is one file, `src/doppel/languages/<language>.py`, exposing `SPEC`, a `LanguageSpec` (`src/doppel/spec.py`). doppel finds it by scanning that folder: no list names it, and `--help` shows it. No engine file changes. Its tests go in `tests/test_<language>.py`, transliterating `tests/test_kotlin.py` or `tests/test_swift.py`, and the README gains a "What … compares" section and its skip rules.

To find the node names, parse a small file and print its tree: `doppel.treesitter.parse(source, "<grammar>")` returns the tree, and each node has `type`, `is_named` and `children`. Node names are those of the grammar in the pinned `tree-sitter-language-pack`.

Java, worked through each field. It is the paper check of the boundary: its grammar shapes a call differently from Kotlin and Swift. `a.b.foo(x)` is one flat `method_invocation` whose children are the receiver (`field_access` `a.b`), `.`, the name (`identifier` `foo`, field `name`) and `argument_list`; Kotlin and Swift nest the receiver and the name inside the callee instead.

| Field | What it answers | Java |
|---|---|---|
| `name` | The language's name, in `--help` | `"java"` |
| `extensions` | The files the language owns | `{".java"}` |
| `grammar` | The tree-sitter grammar for a file | `lambda path: "java"` |
| `skips` | Whether a file or folder is left out; the first path part is the scanned folder's name, context only | Gradle's and Maven's: `build`, `.gradle`, `target`, test source sets under `src`, files ending in `Test.java` or `Tests.java` |
| `candidates` | The functions to compare | `CandidateRule(types={"method_declaration"}, body="block", enclosing={"method_declaration", "constructor_declaration", "lambda_expression"})`: an abstract or interface method has no `block`, and a constructor is not a candidate |
| `named_by` | The child of a candidate that holds its name, printed as written; None when it has none | `node.child_by_field_name("name")`, the `sum` of `int sum(int a)`: unlike Swift's, the field holds only the name, since the return type is the `type` field |
| `comments` | Dropped | `line_comment`, `block_comment` |
| `identifiers` | Generic markers, kept as text in call position | `identifier`, `type_identifier` |
| `literals` | Generic markers | `decimal_integer_literal`, `hex_integer_literal`, `octal_integer_literal`, `binary_integer_literal`, `decimal_floating_point_literal`, `hex_floating_point_literal`, `string_literal`, `character_literal`, `true`, `false`, `null_literal` |
| `parenthesized` | Unwrapped when they hold one expression | `parenthesized_expression` |
| `calls` | Each call node type, and the child that names the callee | `method_invocation`: `node.child_by_field_name("name")`, the `foo` of `a.b.foo(x)`, a direct child, so the receiver needs no help; `object_creation_expression`: `node.child_by_field_name("type")`, the type of `new ArrayList<String>()`; `method_reference`: its last named child, the `valueOf` of `String::valueOf` |
| `members` | For a callee that is not a name, the child holding the name | `method_invocation` never needs one, since its name is a direct child. Constructors do: `generic_type` → its first named child (`ArrayList` in `ArrayList<String>`), `scoped_type_identifier` → its last named child (`ArrayList` in `java.util.ArrayList`) |
| `kept_tokens` | Unnamed tokens that change meaning | Operators where one node type covers several: `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `&&`, `\|\|`, `!`, `=`, `+=`, `-=`, `++`, `--`. `return`, `throw`, `break` and `continue` need none: each has its own statement node type |
| `interpolations` | Child types that make a literal structure | `string_interpolation`, the `\{foo(x)}` of a string template |

Nothing in that table needs an engine change: every callee, flat or nested, is a direct child of the call node or reached through `members`.

## Credits

doppel starts from [dryer](https://github.com/unclebob/dryer) by Robert C. Martin, released under the 0BSD licence. The fingerprint and score (`shape.py`), the pairing (`scan.py`), the data types (`model.py`), the tree-sitter helpers (`treesitter.py`), the folder walk (`discover.py`), the function extraction (`extract.py`), the candidate rule's nesting check (`spec.py`), the text report (`report.py`), the command line (`cli.py`) and the git changed-files logic (`changed.py`) are copied or adapted from it, and the normalizer (`astnorm.py`) is reworked from dryer's to read each language's node roles from its spec. Each copied file names the dryer file it came from.
