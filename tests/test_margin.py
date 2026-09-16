# -*- coding: utf-8 -*-
"""Sending tags out to a clear band beside the drawing."""

from __future__ import division

from tagtwin import declutter, margin

CASES = []


def case(func):
    CASES.append(func)
    return func


#: a riser: pipework between x = 0 and x = 10, running up
RISER = [(1, 2.0, 9.0), (2, 8.0, 7.0), (3, 3.0, 5.0), (4, 7.0, 3.0), (5, 5.0, 1.0)]


@case
def test_the_band_clears_the_drawing():
    band = margin.band_for([(x, y) for _, x, y in RISER], gutter=2.0)
    assert band.left == 0.0          # leftmost pipe at x = 2, less the gutter
    assert band.right == 10.0        # rightmost at x = 8, plus the gutter
    assert band.centre == 5.0
    assert band.bounds == (2.0, 8.0)


@case
def test_each_tag_goes_to_its_nearer_side():
    band, placements = margin.plan(RISER, gutter=2.0)
    by_key = dict((p.key, p) for p in placements)
    assert by_key[1].side == margin.LEFT      # x = 2, left of centre
    assert by_key[2].side == margin.RIGHT     # x = 8
    assert by_key[3].side == margin.LEFT
    assert by_key[4].side == margin.RIGHT
    assert margin.summarise(placements) == {margin.LEFT: 2, margin.RIGHT: 3}


@case
def test_a_tag_keeps_its_own_height_so_the_leader_stays_short():
    """Straight out sideways, not diagonally across the drawing."""
    _band, placements = margin.plan(RISER, gutter=2.0)
    for placement in placements:
        assert placement.position[1] == placement.anchor[1]


@case
def test_tags_land_outside_everything_they_label():
    band, placements = margin.plan(RISER, gutter=2.0)
    for placement in placements:
        if placement.side == margin.LEFT:
            assert placement.position[0] < band.bounds[0]
        else:
            assert placement.position[0] > band.bounds[1]


@case
def test_the_band_can_be_taken_from_the_whole_view_not_just_the_tagged_parts():
    """Untagged pipework still has to be cleared."""
    everything = [(0.0, 0.0), (20.0, 12.0)]
    band = margin.band_for(everything, gutter=1.0)
    _band, placements = margin.plan(RISER, gutter=1.0, band=band)
    assert all(p.position[0] in (-1.0, 21.0) for p in placements)


@case
def test_a_column_stacks_without_overlapping_or_reordering():
    """margin.plan only picks the column; declutter does the stacking."""
    entries = [(n, 2.0, 10.0 - 0.05 * n) for n in range(12)]   # all left, bunched
    _band, placements = margin.plan(entries, gutter=3.0)
    labels = [declutter.Label(p.key, p.position, 1.0, 0.25) for p in placements]
    result = declutter.resolve(labels, gap=0.05)

    assert result.remaining_overlaps == 0
    heights = [l.position[1] for l in labels]
    assert heights == sorted(heights, reverse=True), 'leaders would cross'
    # and they stay in one column
    assert len(set(round(l.position[0], 6) for l in labels)) == 1


@case
def test_leader_reach_is_reported():
    _band, placements = margin.plan(RISER, gutter=2.0)
    by_key = dict((p.key, p) for p in placements)
    assert by_key[1].reach == 2.0        # x = 2 out to the band at x = 0
    assert by_key[2].reach == 2.0        # x = 8 out to the band at x = 10
    # the pipe nearest the middle has the longest leader, as it must
    assert by_key[5].reach == max(p.reach for p in placements)


@case
def test_no_entries_is_safe():
    band, placements = margin.plan([], gutter=2.0)
    assert placements == []
    assert band.column_for(0.0) in (margin.LEFT, margin.RIGHT)
    assert margin.summarise([]) == {}


@case
def test_everything_on_one_side_still_works():
    entries = [(n, 1.0, float(n)) for n in range(4)]
    band, placements = margin.plan(entries, gutter=2.0)
    assert band.centre == 1.0
    # ties go right, and nothing lands inside the drawing
    assert all(p.position[0] in (-1.0, 3.0) for p in placements)
