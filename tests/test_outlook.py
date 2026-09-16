# -*- coding: utf-8 -*-
"""Deciding whether a run is worth doing.

The bug these cover: a sanitary riser matched well on the elements that carry
tags, but only about a third of the view's elements overall - and the run was
refused on that overall figure, so nothing was copied at all.
"""

from __future__ import division

from tagtwin import outlook
from tagtwin.matching import SolveResult

CASES = []


def case(func):
    CASES.append(func)
    return func


class Item(object):
    """Stands in for a collected annotation."""

    def __init__(self, kind, host_ids=(), references_model=True):
        self.kind = kind
        self.host_ids = list(host_ids)
        self.references_model = references_model


TAG = 'Tag'
DIMENSION = 'Dimension'
TEXT = 'Text note'
NEEDS_ALL = (DIMENSION,)


@case
def test_a_tag_needs_one_matched_host():
    items = [Item(TAG, [10]), Item(TAG, [11])]
    result = outlook.assess(items, {10: 99}, NEEDS_ALL)
    assert (result.placeable, result.blocked) == (1, 1)
    assert result.hosted_total == 2 and result.hosted_matched == 1
    assert result.is_worth_running


@case
def test_a_multi_reference_tag_survives_a_partial_match():
    """Tagging three elements where one matched still gives a usable tag."""
    result = outlook.assess([Item(TAG, [1, 2, 3])], {2: 22}, NEEDS_ALL)
    assert result.placeable == 1


@case
def test_a_dimension_needs_every_reference():
    """A dimension measures between specific elements - losing one loses it."""
    items = [Item(DIMENSION, [1, 2]), Item(DIMENSION, [3, 4])]
    result = outlook.assess(items, {1: 11, 2: 22, 3: 33}, NEEDS_ALL)
    assert (result.placeable, result.blocked) == (1, 1)


@case
def test_free_annotations_always_place():
    items = [Item(TEXT, references_model=False),
             Item(TEXT, references_model=False)]
    result = outlook.assess(items, {}, NEEDS_ALL)
    assert result.placeable == 2 and result.free == 2
    assert result.is_worth_running
    assert result.host_coverage == 0.0       # nothing hosted, so nothing to cover


@case
def test_an_annotation_hosted_on_nothing_is_blocked():
    result = outlook.assess([Item(TAG, [])], {}, NEEDS_ALL)
    assert (result.placeable, result.blocked) == (0, 1)
    assert not result.is_worth_running


@case
def test_the_riser_case_low_coverage_but_every_tag_lands():
    """The bug: refused because most of the view is untagged pipework.

    300 elements, 12 of them tagged. All 12 tagged elements matched, so every
    annotation can be placed - even though only a third of the view paired up.
    """
    tagged = list(range(1, 13))
    items = [Item(TAG, [host]) for host in tagged]
    id_map = dict((host, 1000 + host) for host in tagged)      # all tags land
    id_map.update(dict((n, 1000 + n) for n in range(100, 190)))  # some pipework
    result = outlook.assess(items, id_map, NEEDS_ALL)

    assert result.placeable == 12 and result.blocked == 0
    assert result.host_coverage == 1.0
    assert result.is_worth_running, 'this is exactly the run that got refused'
    assert '12 of 12 annotations' in result.summary()
    assert '100% of tagged elements' in result.summary()


@case
def test_nothing_placeable_is_reported_as_such():
    items = [Item(TAG, [1]), Item(DIMENSION, [1, 2])]
    result = outlook.assess(items, {}, NEEDS_ALL)
    assert not result.is_worth_running
    assert result.placeable == 0
    assert result.summary() == 'none of the 2 annotations can be placed'


@case
def test_empty_source_is_safe():
    result = outlook.assess([], {}, NEEDS_ALL)
    assert not result.is_worth_running
    assert result.total == 0
    assert result.share == 0.0
    assert result.summary() == 'nothing to copy'


@case
def test_share_and_host_coverage():
    items = [Item(TAG, [1]), Item(TAG, [2]), Item(TAG, [3]), Item(TAG, [4])]
    result = outlook.assess(items, {1: 11, 2: 22}, NEEDS_ALL)
    assert result.share == 0.5
    assert result.host_coverage == 0.5


# --------------------------------------------------------------------------
# the confidence score that used to drive the refusal
# --------------------------------------------------------------------------

class _FakeMatch(object):
    def __init__(self, exact=True, ambiguous=False):
        self.is_exact = exact
        self.ambiguous = ambiguous


class _FakeResult(object):
    def __init__(self, coverage, matches, exact, ambiguous):
        self.coverage = coverage
        self.matches = [_FakeMatch()] * matches
        self.exact_count = exact
        self.ambiguous_count = ambiguous


class _FakeAlignment(object):
    def __init__(self, unambiguous=True):
        self.is_unambiguous = unambiguous


def _confidence(coverage, matches=100, exact=100, ambiguous=0, unambiguous=True):
    solve = SolveResult(_FakeAlignment(unambiguous),
                        _FakeResult(coverage, matches, exact, ambiguous), 0)
    return solve.confidence()


@case
def test_penalties_no_longer_compound_into_poor():
    """Three stacked discounts used to drag a decent match below the floor."""
    # a half-matched view with some relaxed matches and a rival transform
    score = _confidence(0.5, exact=60, ambiguous=0, unambiguous=False)
    assert score > 0.4, score
    # the old formula: 0.5 * (0.75 + 0.25*0.6) * 0.85 = 0.3825 -> "poor"
    old = 0.5 * (0.75 + 0.25 * 0.6) * 0.85
    assert old < 0.4 and score > old


@case
def test_confidence_still_tracks_coverage():
    assert _confidence(1.0) == 1.0
    assert _confidence(0.5) == 0.5
    assert _confidence(0.0) == 0.0
    # and a worst-case discount never falls below the floor
    worst = _confidence(1.0, exact=0, ambiguous=100, unambiguous=False)
    assert 0.55 <= worst <= 0.6, worst
