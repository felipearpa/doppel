"""Everything doppel knows about F#.

Node names are those of the ionide/tree-sitter-fsharp grammar shipped in
tree-sitter-language-pack 1.25.2.
"""

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from doppel.spec import LanguageSpec
from doppel.treesitter import child_of_type, descendants, first_named, last_named


# A function in a lambda or a member is not compared; one in a value is.
_ENCLOSING = frozenset({"fun_expression", "function_expression", "member_defn"})

_COMMENTS = frozenset({"line_comment", "block_comment", "xml_doc"})

# `bin` and `obj` hold .NET build output.
_FOLDERS = frozenset({"bin", "obj", "test", "tests"})


def _skips(path: PurePosixPath) -> bool:
    """At any depth, case-sensitive. The first part is the walked folder's name: context only."""

    below = path.parts[1:]
    return bool(_FOLDERS.intersection(below)) or any(
        part.endswith(("Test", "Tests", "Test.fs", "Tests.fs")) for part in below
    )


@dataclass
class _Binding:
    left: object
    returns: object = None
    body: list = field(default_factory=list)
    past_equals: bool = False


def _bindings(defn) -> list[_Binding]:
    """Each binding of a `function_or_value_defn`: its left part, the return
    type written beside it, and what follows its `=`.

    One node holds a whole `let rec … and …` group as loose neighbours: left
    part, `: type`, `=`, body, then `and` and the next binding.
    """

    bindings = []
    for child in defn.children:
        if child.type in ("function_declaration_left", "value_declaration_left"):
            bindings.append(_Binding(child))
        elif not bindings or child.type == "and":
            continue
        elif child.type == "=":
            bindings[-1].past_equals = True
        elif bindings[-1].past_equals:
            bindings[-1].body.append(child)
        elif child.is_named:
            bindings[-1].returns = child
    return bindings


_MODIFIERS = frozenset({b"private", b"internal", b"public", b"inline"})


def _identifier(node):
    return next((child for child in descendants(node) if child.type in ("identifier", "op_identifier")), node)


def _head(left):
    """A function's left part as its attributes or None, its name, its
    parameters, and the return type written inside it or None; None when the
    left part destructures. A value's head has no parameter.

    `let f x = …` is a `function_declaration_left`, and so is `let f x : int
    = x` on one line, the type beside it. With the body on the lines below, or
    after `let rec`, a return type makes the left part a
    `value_declaration_left` holding an `identifier_pattern`, the return type
    joined to the last parameter in a `typed_pattern`; after `and`, so does an
    attribute, under an `attribute_pattern`. A plain or typed value is an
    `identifier_pattern` with no parameter.
    """

    if left.type == "function_declaration_left":
        # `let private f x`: the access modifier is a named node before the name.
        parameters = child_of_type(left, "argument_patterns")
        name = child_of_type(left, "identifier", "op_identifier", "active_pattern")
        return None, name, _arguments(parameters), None
    attributes = None
    # `let private f x : int`: the access modifier is a named node before the pattern.
    pattern = next((child for child in left.named_children if child.type != "access_modifier"), None)
    if pattern is not None and pattern.type == "attribute_pattern":
        attributes = child_of_type(pattern, "attributes")
        pattern = child_of_type(pattern, "identifier_pattern")
    if pattern is None or pattern.type != "identifier_pattern":
        return None
    name, *parameters = pattern.named_children
    # After an attribute, `private`, `internal`, `public` and `inline` are read
    # as the name, the real name as the first parameter. With two of them,
    # the second is read so too, and the name and parameters are nested in
    # one more `identifier_pattern`.
    while name.text in _MODIFIERS and parameters:
        name, *parameters = parameters
        if not parameters and name.type == "identifier_pattern" and len(name.named_children) > 1:
            name, *parameters = name.named_children
    parameters, returns = _split_return(parameters)
    return attributes, _identifier(name), parameters, returns


def _arguments(patterns):
    """The parameters of an `argument_patterns`, a `_` included: the grammar
    gives it as a token, not a named node."""

    if patterns is None:
        return []
    return [child for child in patterns.children if child.is_named or child.type == "_"]


def _split_return(parameters):
    """The parameters and the return type joined to the last of them in a
    `typed_pattern`, or None."""

    if parameters and parameters[-1].type == "typed_pattern":
        typed = parameters[-1].named_children
        return [*parameters[:-1], typed[0]], typed[-1]
    return parameters, None


def _pieces(attributes, name, parameters, returns, body) -> tuple:
    pieces = (*attributes, name, *map(_parameter, parameters), returns, *body)
    return tuple(piece for piece in pieces if piece is not None)


def _parameter(node):
    """`(x: int)` is a `typed_pattern` between loose parentheses in a
    `function_declaration_left` and a `paren_pattern` in a
    `value_declaration_left`; a plain `x` is a `long_identifier` in one and an
    `identifier_pattern` in the other. Both shapes are given as one node.
    """

    if node.type == "paren_pattern" and len(node.named_children) == 1:
        node = node.named_children[0]
    if node.type in ("long_identifier", "identifier_pattern") and len(node.named_children) == 1:
        return _identifier(node)
    return node


def _is_function(head) -> bool:
    """`let Some y = opt` destructures a value with the shape of a function;
    the grammar cannot tell. A union case is capitalized and takes one
    pattern, so a capitalized name with one parameter is read as one.
    """

    if head is None or not head[2]:
        return False
    _attributes, name, parameters, _returns = head
    return not (name.type == "identifier" and name.text[:1].isupper() and len(parameters) == 1)


def _lambda(body):
    """A value's right side that is directly a lambda, as the parameters and
    the body of a function; None for any other value.

    `fun a b -> …` gives its parameters as a `function_declaration_left`
    does; `function | … -> …` has none, its rules are its body.
    """

    named = [child for child in body if child.type not in _COMMENTS]
    if len(named) != 1 or named[0].type not in ("fun_expression", "function_expression"):
        return None
    lambda_ = named[0]
    if lambda_.type == "function_expression":
        return [], [child_of_type(lambda_, "rules")]
    parameters = child_of_type(lambda_, "argument_patterns")
    arrow = next((index for index, child in enumerate(lambda_.children) if child.type == "->"), None)
    if parameters is None or arrow is None:
        return None
    return _arguments(parameters), lambda_.children[arrow + 1 :]


def _attributes_before(defn):
    """The attributes written above a `let`: the grammar gives them as the
    node before it, outside it, and they belong to its first binding."""

    sibling = defn.prev_named_sibling
    while sibling is not None and sibling.type in _COMMENTS:
        sibling = sibling.prev_named_sibling
    return sibling if sibling is not None and sibling.type == "attributes" else None


def _method(member):
    """A member that takes parameters as its pieces: its attributes, its
    name, each parameter, its return type, then its body; None for a
    property, an abstract member, `member val` or a constructor.

    The name is the last part of `this.Name`. A return type is joined to the
    last parameter in a `typed_pattern`, as in a `value_declaration_left`; a
    property's is a loose `: type`.
    """

    defn = child_of_type(member, "method_or_prop_defn")
    if defn is None:
        return None
    attributes = [child for child in member.named_children if child.type == "attributes"]
    head, body = [], None
    for child in defn.children:
        if body is not None:
            body.append(child)
        elif child.type == "=":
            body = []
        elif child.type == ":":
            return None
        elif child.is_named and child.type not in ("property_or_ident", "type_arguments", *_COMMENTS):
            head.append(child)
    property_ = child_of_type(defn, "property_or_ident")
    if property_ is None:
        return None
    name = last_named(property_)
    # After an access modifier, `inline` is read as the name and `this.Name`
    # as the first parameter.
    if name.text == b"inline" and head and head[0].type == "identifier_pattern":
        name = head.pop(0)
        while name.named_children:
            name = name.named_children[-1]
    # `member this.P with get () = …` has no `=` of its own.
    if body is None or not head:
        return None
    parameters, returns = _split_return(head)
    return _pieces(attributes, name, parameters, returns, body)


def _functions(root) -> list[tuple]:
    """Each function, method and value that is directly a lambda, not nested
    in another function, a lambda or a member, as its pieces: its
    attributes, above its `let`, after `and` or on its member, its name, each
    parameter, its return type, then its body. Every head is given in this
    one shape, whichever node kind the grammar gives it, so a function of a
    group and its copy written as a plain `let`, a copy with a return type
    and one without, or `let f = fun x -> …` and `let f x = …`, line up.
    """

    found = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "member_defn" and (method := _method(node)) is not None:
            found.append(method)
        if node.type in _ENCLOSING:
            continue
        if node.type != "function_or_value_defn":
            stack.extend(reversed(node.children))
            continue
        outer = _attributes_before(node)
        for index, binding in enumerate(_bindings(node)):
            head = _head(binding.left)
            lambda_ = _lambda(binding.body) if head is not None and not head[2] else None
            if not _is_function(head) and lambda_ is None:
                stack.extend(reversed(binding.body))
                continue
            attributes, name, parameters, inner_returns = head
            body = binding.body
            if lambda_ is not None:
                parameters, body = lambda_
            above = outer if index == 0 else None
            found.append(_pieces((above, attributes), name, parameters, binding.returns or inner_returns, body))
    return sorted(found, key=lambda pieces: pieces[0].start_byte)


# The operands that are functions when nothing follows a pipe or a
# composition: `xs |> List.length`, `List.length <| xs`, `f >> g`. A custom
# operator is not listed, so the function after it stays generic.
_FUNCTION_SIDES = {
    "|>": ("right",),
    "||>": ("right",),
    "|||>": ("right",),
    "<|": ("left",),
    "<||": ("left",),
    "<|||": ("left",),
    ">>": ("left", "right"),
    "<<": ("left", "right"),
}


def _operation(node):
    """The operator of `a op b`, and each operand that is the function called.

    The grammar reads `a + f x` as `(a + f) x` and `xs |> List.map f` as
    `(xs |> List.map) f`, whatever the operator: when the expression heads an
    application, in parentheses or not, its right operand is the function called.
    """

    # A comment between the stages of a pipeline is a named child too.
    operands = [child for child in node.named_children if child.type not in _COMMENTS]
    if len(operands) != 3:
        return None
    left, operator, right = operands
    sides = {"left": left, "right": right}
    called = [operator, *(sides[side] for side in _FUNCTION_SIDES.get(operator.text.decode(), ()))]
    # `(a + f) xs` heads the application through its parentheses.
    head = node
    while head.parent.type == "paren_expression":
        head = head.parent
    parent = head.parent
    if parent.type == "application_expression" and parent.named_children[0] == head:
        called.append(right)
    return tuple(called)


def _name(pieces):
    name = next(piece for piece in pieces if piece.type != "attributes")
    return name if name.type in ("identifier", "op_identifier", "active_pattern") else None


SPEC = LanguageSpec(
    name="f#",
    extensions=frozenset({".fs"}),
    grammar=lambda path: "fsharp",
    skips=_skips,
    candidates=_functions,
    named_by=_name,
    comments=_COMMENTS,
    # An operator is a named `infix_op` or `prefix_op` node, not a token:
    # listed here, it keeps its text as a child in call position of its expression.
    # A wildcard is a name like any other: a `_` token among the parameters
    # of a `function_declaration_left` or a lambda, a `wildcard_pattern` elsewhere.
    identifiers=frozenset({"identifier", "op_identifier", "infix_op", "prefix_op", "_", "wildcard_pattern"}),
    # `const` wraps each of these; `()` is left out: `f ()` is a call with no argument.
    literals=frozenset(
        {
            "bool",
            "char",
            "string",
            "verbatim_string",
            "triple_quoted_string",
            "bytearray",
            "verbatim_bytearray",
            "int",
            "int16",
            "int32",
            "int64",
            "uint16",
            "uint32",
            "uint64",
            "nativeint",
            "unativeint",
            "byte",
            "sbyte",
            "xint",
            "bignum",
            "decimal",
            "float",
            "ieee32",
            "ieee64",
        }
    ),
    # The grammar wraps one name in a `long_identifier` in some places and not
    # in others, with nothing in the source to tell them apart: unwrapped, a
    # name has one shape.
    parenthesized=frozenset({"paren_expression", "long_identifier"}),
    # `f x y` is `(f x) y`, so each application's first child leads to the name.
    # `return x` is a `prefixed_expression` too, with no `prefix_op`.
    calls={
        "application_expression": first_named,
        "infix_expression": _operation,
        "prefixed_expression": lambda node: child_of_type(node, "prefix_op"),
    },
    # `List.map` is `long_identifier_or_op` → `long_identifier` → `List`, `.`,
    # `map`; `x.Foo(1).Bar` is a `dot_expression` ending in `Bar`.
    members={"long_identifier_or_op": last_named, "long_identifier": last_named, "dot_expression": last_named},
    # `return`, `yield` and their `!` forms share `prefixed_expression`; `let!`
    # and `use!` share `function_or_value_defn` with `let`. `:>` and `:?>`
    # share `typecast_expression`.
    kept_tokens=frozenset(
        {"return", "return!", "yield", "yield!", "let!", "use", "use!", "do!", ":>", ":?>"}
    ),
    # `$"…{f x}…"`: the text around the expression stays out of the structure.
    interpolations=frozenset({"format_string", "format_triple_quoted_string"}),
)
