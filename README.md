# doppel

doppel finds functions whose structure is similar and scores how close each pair is. It reads Kotlin (`.kt`), Swift (`.swift`) and F# (`.fs`); `doppel --help` lists the languages it knows.

Each function is normalized: the names of the functions called, the operators and the shape of the code stay, while local names, literals and comments do not. The score of a pair is the share of structural fingerprints the two functions have in common (Jaccard similarity), from 0 to 1. Functions are compared only with functions of the same language. Five copies of one function make ten pairs, and with no focus each pair is listed once, so they take four groups.

## Install

```bash
uv sync
```

The first run in each language downloads that language's parser, so it needs network; once downloaded, a parser loads without it (see Standard error for a parser that cannot be loaded).

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
uv run doppel tests/fixtures/fsharp-renamed           # the same, in F#
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
- `--changed-functions`: the functions in focus are those an uncommitted change touched, each compared, as with `--changed`, against every function scanned. A function is touched when a line in its range changed since the last commit (`git diff HEAD`, staged or not), and every function of an untracked file is touched; before the first commit, every function of each file `git status` reports is. A function's range runs from its first annotation or attribute (`@Deprecated`, `@discardableResult`, F#'s `[<Obsolete>]`) to its last line that is not a comment, its closing brace in Kotlin and Swift, so editing only an annotation or attribute touches it, while a doc comment or other comment above the function lies outside the range and editing only it touches nothing. Deleting lines touches only the line just above them (or line 1, for a deletion at the top of a file), so the function above a deletion counts only when that line is its last line: deleting a comment separated from the function by a blank line touches nothing. An edit outside every compared function, or inside code doppel does not compare (a Swift `init` or computed property, a function shorter than `--min-lines` or `--min-nodes`), touches nothing; an edit inside a nested function or lambda touches the function around it. A copy that existed before the change is listed when the change touches either function, under the touched one. As with `--changed`, git is asked where the scanned files are: in each named folder or named file's folder, or in the current directory when no path is named, so a folder above the current directory or in another repository works. Run outside a git repository, it prints git's reason and exits 1. With `--changed` too, the functions in focus of both head groups.
- `--focus`: the path arguments name the files to report on, and the current directory is scanned: the functions in focus are those in a named file, their copies being any function scanned, so a function copied from a file that was not named is found. Every argument is a path, never a fragment, and at least one is required. A named file is also scanned, so a test file named this way is compared; a named folder is walked with the usual skips (see What is skipped), so its test files are left out unless named themselves. A named path that does not exist (`doppel: Gone.kt does not exist; skipped`), a file doppel does not read (`doppel: README.md is not a source file doppel reads; skipped`) or a folder holding none (`doppel: docs holds no source file doppel compares; skipped`) is named on standard error and skipped, and the run goes on with the rest. When no named path is a source file doppel reads, doppel prints `doppel: --focus names no source file doppel reads` and exits 1, printing nothing on standard output. A named file whose functions are all shorter than `--min-lines` or `--min-nodes` lists nothing and exits 0. With `--changed` or `--changed-functions` too, the functions in focus of each head groups, and git is asked in the current directory and in each named file's folder. So the list of files a change touched, deleted files and READMEs included, can be passed as it is.
- `-h`, `--help`: print the help, with each language and its file extensions, and exit 0.

A bad option prints the reason and the help on standard error and exits 1, and so does `--focus` with no path argument. When git fails for `--changed` or `--changed-functions` (outside a git repository, or, under `--changed-functions`, on a committed source file doppel cannot read), doppel prints git's reason after the option's name and exits 1, and `--focus` naming no source file doppel reads exits 1 as well, as does a language whose parser cannot be loaded (see Standard error); otherwise doppel exits 0.

### Reading the report from an agent

A project whose agents run doppel can paste this paragraph into its `AGENTS.md`:

> doppel prints one group per function that has a copy: a heading with the function's location (`file:start-end`) and name, then one line per copy with its score, location and name, closest first. With `--changed`, `--changed-functions` or `--focus`, each function in focus that has a copy heads its own group, and that group lists all of its copies. With no focus, each pair is printed once, under whichever function comes first, so a function's copies are split between its own group and the groups of the functions before it; read the whole report before saying a function has no copy. Cite a function by its location, not by its name: two functions can share a name. `No duplicate candidates found.` means nothing was listed. doppel writes no file; a `.doppel` folder an earlier version left behind can be deleted.

### What is skipped

Folders `.git`, `.hg`, `.svn`, `.idea`, `.vscode` and `.doppel` are never scanned. For Kotlin, only `.kt` files are read (not `.kts` scripts), and these are skipped: `build` and `.gradle` folders above `src/` (a package folder called `build` inside `src/` is compared); any source set under `src/` whose name contains "test" (`test`, `androidTest`, `commonTest`, `testFixtures`); files ending in `Test.kt`, `Tests.kt` or `Spec.kt`. Scanning `src` still skips its test source sets, but a test file or test folder named as an argument (`src/test`) is compared; inside a named folder, files ending in `Test.kt`, `Tests.kt` or `Spec.kt` are still skipped unless they are named themselves. The scanned folder's own name never causes a skip: a project checked out in a folder called `build` is scanned. Run doppel from the module or project root, not from inside a source set: scanning `src/main` directly, a package folder called `build` is taken for build output and skipped.

For Swift, these are skipped at any depth: `.build`, `DerivedData`, `Pods` and `Carthage` folders (tool output and dependency checkouts); folders whose name ends in `Tests` (`Tests`, `AppTests`, `AppUITests`); files ending in `Tests.swift`. As for Kotlin, a test file or folder named as an argument (`Tests/AppTests`) is compared, though files ending in `Tests.swift` and folders ending in `Tests` inside a named folder are still skipped unless named themselves, and the scanned folder's own name never causes a skip.

For F#, these are skipped at any depth: `bin` and `obj` folders (build output); folders named `test` or `tests`, or whose name ends in `Test` or `Tests` (`Billing.Tests`, `Core.UnitTests`); files ending in `Test.fs` or `Tests.fs`. Matching is case-sensitive, so `Latest.fs` and a `Contest` folder are compared. As for Swift, a test file or folder named as an argument (`tests`, `src/Billing.Tests`) is compared, though test files, test folders and `bin`/`obj` folders inside a named folder are still skipped unless named themselves, and the scanned folder's own name never causes a skip.

A folder is left out of the walk only when every language skips it, so a Kotlin `build` folder is still walked for Swift files, and a Swift `.build` folder for Kotlin files; the files each language skips are still left out.

### Standard error

Each file the grammar cannot fully parse is named in a warning (`doppel: <file> has parse errors; compared as parsed`); the functions it could read are still compared. A file's language is told by its extension alone, so every `.fs` file is read as F#, GLSL fragment shaders (and Forth) included: a shader the F# grammar rejects, one with a `#version` line for instance, gets this warning on every run and is counted with the files with parse errors, while one it parses gets none; neither has yielded a function in the shaders tried. A source file doppel cannot open, for lack of permission for instance, is named on standard error (`doppel: <file> cannot be read; skipped`) and left out, and the run goes on with the other files. This holds whatever the options, with one exception: under `--changed-functions`, git cannot compare a committed file it cannot read, so doppel prints `doppel: --changed-functions needs git: ` followed by git's reason and exits 1.

When a language's parser cannot be loaded, most often on its first use with no network to download it, doppel prints one line naming the language and the reason, such as `doppel: the F# parser cannot be loaded: Download error: Failed to fetch manifest from …`, prints no report and no summary line, and exits 1: it compares nothing rather than a report that leaves out a language. A Kotlin or Swift project holding one `.fs` shader stops this way too, until it is run once with network. A parser already downloaded loads with no network.

Each run that scans and exits 0, even one that finds no source file, ends with one summary line, whose count of files scanned leaves out the files that could not be read:

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

## What F# compares

A `let` that takes parameters is compared as a function (`let total orders = …`, and `let onClick _ = …`, whose one parameter is `_`), with or without a return type (`let total orders : decimal = …`), and so is each function of a `let rec … and …` group, under its own name and lines, an attribute after `and` included (`and [<Obsolete>] f x = …`): the grammar reads a whole group as one node, and doppel splits it. A function of a group and its copy written elsewhere as a plain `let` score 1.00, since neither `let rec` nor `and` counts. An active pattern is a function too, named by the pattern as written (`let (|Even|Odd|) n = …` is `(|Even|Odd|)`, `let (|Int|_|) s = …` is `(|Int|_|)`): its number of cases and whether it is partial count, the case names do not, so a renamed copy scores 1.00. Local names, parameter and type names, literals and comments do not count, and a wildcard `_` parameter is a name like any other: `let f _ x = g x` and `let f a x = g x` score 1.00, as do `fun _ x -> …` and `fun a x -> …`. A wildcard in a pattern does not line up with a name, since the grammar wraps a name in more nodes: a `match` whose second rule is `| _ -> step x` scored 0.62 against the same with `| other -> step x` (first rule `| 0 -> 1`). A typed wildcard does not line up with a typed name, since the grammar gives each its own shape: `let f (_: int) x = g x` scored 0.67 against `let f (a: int) x = g x`. An attribute counts as structure, above the `let` or after `and`, so adding or removing one lowers the score, while its name, like a type name, does not count (`[<Obsolete>]` against `[<Deprecated>]`). The name of the function called counts, in every call shape:

- `f x` and `List.map f xs`: only the last part of a dotted name is kept, as in Kotlin and Swift;
- a method call, plain or in a chain: `obj.Method(x)`, and both `Foo` and `Bar` in `x.Foo(1).Bar 2`;
- a call after an operator: the grammar reads `a + f x` as `(a + f) x` and `xs |> List.map g` as `(xs |> List.map) g`, whatever the operator, so the function after it is kept, through every stage of a pipeline, and in parentheses too (`(a + f) xs`);
- a function piped or composed with nothing after it: the right side of `|>`, `||>` and `|||>`, the left side of `<|`, `<||` and `<|||`, and both sides of `>>` and `<<`, so `xs |> List.length` and `xs |> List.sum` differ.

Every operator counts by its text, between two operands (`a + b`, `x :: xs`, `xs |> f`) or in front of one (`-a` against `+a`). An operator a project defines is kept too, but doppel does not know which of its sides is a function: with nothing after it, the function next to it does not count (`xs |>> List.length` and `xs |>> List.sum` score 1.00), while one that takes an argument (`xs |>> List.map f`) does. The grammar sometimes wraps a single name in one more node, with nothing in the source to tell why; doppel unwraps it, so a name has one shape wherever it is written.

A return type is structure, as a written type is in Kotlin and Swift, so a copy that differs only by one scores below 1.00. The grammar gives a typed and an untyped head different shapes; doppel compares every head as its name, its parameters and its return type, so the type is the only difference there. Access modifiers and `inline` are not part of it: `let private f x : int = …` and `and [<Obsolete>] private f x = …` are compared like any function, under their own name. Measured on a function whose body is a two-stage pipeline (`orders |> List.filter isPaid |> List.sumBy amount`), a copy without its return type scored 0.94 when the parameters were typed (`let total (orders: Order list) : decimal = …`) and 0.84 when they were not; with `Result<decimal, decimal>` as the return type, 0.78 and 0.68. On a shorter body (`let inc (x: int) : int = x + step x`), 0.90 and 0.76. Such a copy is often missed at the default threshold of 0.82 when the return type is long, the parameters untyped or the body short.

A method on a type is compared as a function, under the last part of its name, without `this.` (`member this.Total (customer: string) = …` is `Total`): a `member`, `static member`, `override` or `default` that takes parameters, `()` included, an interface's method and an operator (`static member (+) (a, b) = …`) too. Its attributes, parameters, return type and body count, as in a `let` function; `member`, `static`, `override`, access modifiers and `inline` do not, so a static method and its copy as an instance method score 1.00. A property is not compared: a member without parameters (`member this.Count = …`, `member this.Count : int = …`), one with `get` or `set`, `member val`, and an abstract member, nor is a constructor (`new (x) = …`).

A `let` whose right side is directly a lambda is compared as a function, under its own name, wherever a `let` function would be (at the top level, in a module, in a `let rec … and …` group, in a class body, inside a top-level value): `let add = fun a b -> …` as one taking `a` and `b`, `let describe = function | … -> …` as one with no parameter whose body is its rules. A value that holds a lambda further in is not: a list or a tuple of lambdas, a lambda in parentheses (`let f = (fun x -> x)`), or one passed to a function (`let f = withLogging (fun x -> …)`). Written the plain way, a `fun` value's copy (`let total orders customer = …` against `let total = fun orders customer -> …`) scores 1.00, since its parameters and body line up. A `function` value's copy written with `match` does not: `match value with` adds a parameter and the expression matched, so the pair scores below 1.00. Measured on two rules calling a function (`| Some order -> show order.Total | None -> "none"`), it scored 0.85; on two rules of arithmetic (`| 0 -> 1 | n -> n * 2`), 0.818, under the default threshold of 0.82; on three rules with a pipeline, 0.92. Such a copy is found when the rules hold more than a line or two of work, and missed when they are short. A lambda value written with its type (`let handler : HttpHandler = fun next ctx -> …`) has the whole annotation counted as its return type. Measured on a three-stage pipeline (`ctx |> readBody |> validate |> respond next`), it scored 0.84 against the same lambda without the annotation, and 1.00 against a plain `let handler next ctx : HttpFuncResult = …`, one type name against another. With a function type on a short body (`let apply : int -> int = fun x -> x + step x`), it scored 0.68 against the same lambda without the annotation and 0.79 against `let apply x : int = x + step x`, both under the default threshold of 0.82.

A `let` without parameters, `_` counting as one, is a value and is not compared, typed or not (`let count : int = 3`), and neither is one that destructures (`let (a, b) = pair`, `let Some y = opt`) or a `let!` or `use!` in a computation expression. The grammar gives `let Some y = opt` the shape of a function, so a capitalized name with exactly one parameter, `_` included (`let Some _ = opt`), is read as a union case being destructured: a function written that way (`let Create x = …`) is not compared. A function defined inside another function, a lambda (`fun`, `function`) or a member is part of it and is not compared on its own; one defined inside a top-level value, such as a test list (`let tests = testList "…" [ let helper x = … ]`), is.

A function's lines run from its first attribute, above the `let`, after `and` or above a member, to the last line of its body that is not a comment. The grammar holds the comments after a function or a method inside it, the doc comment of the next one included, sometimes within the last rule of a `match`; doppel leaves them out, so they count neither toward `--min-lines` nor, under `--changed-functions`, as an edit of the function above them. A doc comment is outside the range of the function it documents, as in Kotlin and Swift.

A `match` or `function` written on one line (`match x with | Some v -> show v | None -> "none"`) is not compared as its rules: the grammar reads the first rule's body as running to the end of the line, the `|` and `->` of the rules after it as operators and their patterns as expressions. A copy with each rule on its own line therefore scores well below 1.00. Measured against that copy, two rules calling a function scored 0.53 with `match` and 0.55 with `function`; three rules each calling a function on the matched value (`| A -> go x | B -> stop x | C -> wait x`), 0.47; two rules of arithmetic (`| 0 -> 1 | n -> n * 2`), 0.41. doppel does not rebuild the rules: the patterns would still be read as expressions, so the pair would still score below 1.00.

## Adding a language

A language is one file, `src/doppel/languages/<language>.py`, exposing `SPEC`, a `LanguageSpec` (`src/doppel/spec.py`). doppel finds it by scanning that folder: no list names it, and `--help` shows it. Its tests go in `tests/test_<language>.py`, transliterating `tests/test_kotlin.py` or `tests/test_swift.py`, and the README gains a "What … compares" section and its skip rules.

To find the node names, parse a small file and print its tree: `doppel.treesitter.parse(source, "<grammar>")` returns the tree, and each node has `type`, `is_named` and `children`. Node names are those of the grammar in the pinned `tree-sitter-language-pack`.

A function is usually one node of the tree. When the grammar does not give it one, `candidates` gives it as a tuple of nodes, its pieces, in source order: the engine normalizes each piece and joins them under one head of its own, and the function's lines run from the first line of its first piece to the last line of its last. `named_by` then receives that tuple and returns the node holding the name. F# does this: a `let rec … and …` group is one node, each of its functions a run of loose children, so every F# function is given as its attributes, the part holding its name and parameters, then its body, a plain `let` too, so that both have the same shape. A function given as one node is normalized as it always was, with no added head. Either way, a function ends at its last line that is not a comment, at any depth: a grammar may hold the comments that follow a function inside its node or among its pieces, as F#'s does.

A call usually has one child in call position. When it has several, its `calls` function returns them as a tuple, and each keeps its name. F# does this: in `a + f x`, read as `(a + f) x`, both the operator and `f` are kept.

Java, worked through each field. It is the paper check of the boundary: its grammar shapes a call differently from Kotlin and Swift. `a.b.foo(x)` is one flat `method_invocation` whose children are the receiver (`field_access` `a.b`), `.`, the name (`identifier` `foo`, field `name`) and `argument_list`; Kotlin and Swift nest the receiver and the name inside the callee instead.

| Field | What it answers | Java |
|---|---|---|
| `name` | The language's name, in `--help` | `"java"` |
| `extensions` | The files the language owns | `{".java"}` |
| `grammar` | The tree-sitter grammar for a file | `lambda path: "java"` |
| `skips` | Whether a file or folder is left out; the first path part is the scanned folder's name, context only | Gradle's and Maven's: `build`, `.gradle`, `target`, test source sets under `src`, files ending in `Test.java` or `Tests.java` |
| `candidates` | The functions to compare, each a node or a tuple of its pieces | `CandidateRule(types={"method_declaration"}, body="block", enclosing={"method_declaration", "constructor_declaration", "lambda_expression"})`: an abstract or interface method has no `block`, and a constructor is not a candidate |
| `named_by` | The node of a candidate that holds its name, printed as written; None when it has none | `node.child_by_field_name("name")`, the `sum` of `int sum(int a)`: unlike Swift's, the field holds only the name, since the return type is the `type` field |
| `comments` | Dropped | `line_comment`, `block_comment` |
| `identifiers` | Generic markers, kept as text in call position; a token listed here is kept too (F#'s `_`) | `identifier`, `type_identifier` |
| `literals` | Generic markers | `decimal_integer_literal`, `hex_integer_literal`, `octal_integer_literal`, `binary_integer_literal`, `decimal_floating_point_literal`, `hex_floating_point_literal`, `string_literal`, `character_literal`, `true`, `false`, `null_literal` |
| `parenthesized` | Unwrapped when they hold one expression | `parenthesized_expression` |
| `calls` | Each call node type, and the child that names the callee, or a tuple of children when several are in call position | `method_invocation`: `node.child_by_field_name("name")`, the `foo` of `a.b.foo(x)`, a direct child, so the receiver needs no help; `object_creation_expression`: `node.child_by_field_name("type")`, the type of `new ArrayList<String>()`; `method_reference`: its last named child, the `valueOf` of `String::valueOf` |
| `members` | For a callee that is not a name, the child holding the name | `method_invocation` never needs one, since its name is a direct child. Constructors do: `generic_type` → its first named child (`ArrayList` in `ArrayList<String>`), `scoped_type_identifier` → its last named child (`ArrayList` in `java.util.ArrayList`) |
| `kept_tokens` | Unnamed tokens that change meaning | Operators where one node type covers several: `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `&&`, `\|\|`, `!`, `=`, `+=`, `-=`, `++`, `--`. `return`, `throw`, `break` and `continue` need none: each has its own statement node type |
| `interpolations` | Child types that make a literal structure | `string_interpolation`, the `\{foo(x)}` of a string template |

Nothing in that table needs an engine change: every callee, flat or nested, is a direct child of the call node or reached through `members`.

## Credits

doppel starts from [dryer](https://github.com/unclebob/dryer) by Robert C. Martin, released under the 0BSD licence. The fingerprint and score (`shape.py`), the pairing (`scan.py`), the data types (`model.py`), the tree-sitter helpers (`treesitter.py`), the folder walk (`discover.py`), the function extraction (`extract.py`), the candidate rule's nesting check (`spec.py`), the text report (`report.py`), the command line (`cli.py`) and the git changed-files logic (`changed.py`) are copied or adapted from it, and the normalizer (`astnorm.py`) is reworked from dryer's to read each language's node roles from its spec. Each copied file names the dryer file it came from.
