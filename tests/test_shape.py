from doppel.shape import K, fingerprints, jaccard


def call(callee: str, argument):
    return [K("call_expression"), [K("symbol"), callee], argument]


def test_given_hand_built_trees_when_fingerprinted_and_scored_then_shared_subtrees_and_leaves_set_the_score():
    left = fingerprints(call("filter", K("literal")))
    right = fingerprints(call("map", K("literal")))

    assert left == {
        '[:call_expression [:symbol "filter"] :literal]',
        '[:symbol "filter"]',
        ":call_expression",
        ":symbol",
        '"filter"',
        ":literal",
    }
    # Shared: the three keyword leaves. Either side: nine fingerprints.
    assert jaccard(left, right) == 3 / 9
    assert jaccard(left, fingerprints(call("filter", K("literal")))) == 1.0
    assert jaccard(left, fingerprints(call("filter", K("symbol")))) < 1.0
