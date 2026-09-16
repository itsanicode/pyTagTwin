# -*- coding: utf-8 -*-
"""Learning a tag arrangement and replaying it.

The point of this path is that it never needs the two views to line up in
space, so these tests deliberately use target views that are nothing like the
source geometrically - only the same kinds of element.
"""

from __future__ import division

from tagtwin import layout

CASES = []


def case(func):
    CASES.append(func)
    return func


PIPE_CW = ('Pipes', 7, 101, 'V')
PIPE_HW = ('Pipes', 7, 102, 'V')
VALVE = ('Pipe Accessories', 31, 101, 'P')
PIPES = 'Pipes'
ACCESSORIES = 'Pipe Accessories'

TAG_PIPE = 900
TAG_VALVE = 901


def sample(signature, category, order, offset, tag_type=TAG_PIPE, elbow=None):
    return layout.TagSample(signature, category, order,
                            layout.Placement(tag_type, offset, elbow))


def host(key, signature, category, order):
    return layout.TargetHost(key, signature, category, order)


# --------------------------------------------------------------------------
# learning
# --------------------------------------------------------------------------

@case
def test_learns_offset_and_tag_type_per_category():
    recipe = layout.learn([
        sample(PIPE_CW, PIPES, (0, 10), (-2.5, 1.0)),
        sample(VALVE, ACCESSORIES, (5, 8), (1.5, 0.5), tag_type=TAG_VALVE),
    ])
    assert recipe.sample_count == 2
    assert recipe.tag_type_for(PIPES) == TAG_PIPE
    assert recipe.tag_type_for(ACCESSORIES) == TAG_VALVE
    assert recipe.tag_type_for('Ducts') is None
    placement, how = recipe.placement_for(PIPE_CW, PIPES)
    assert placement.offset == (-2.5, 1.0)
    assert how == layout.EXACT


@case
def test_the_commonest_tag_type_wins():
    """One stray tag of the wrong type must not decide the category."""
    recipe = layout.learn([
        sample(PIPE_CW, PIPES, (0, 3), (-2, 0), tag_type=TAG_PIPE),
        sample(PIPE_CW, PIPES, (0, 2), (-2, 0), tag_type=TAG_PIPE),
        sample(PIPE_CW, PIPES, (0, 1), (-2, 0), tag_type=999),
    ])
    assert recipe.tag_type_for(PIPES) == TAG_PIPE


@case
def test_staggering_is_preserved_in_reading_order():
    """Three identical valves tagged at three offsets replay in that order."""
    recipe = layout.learn([
        sample(VALVE, ACCESSORIES, (0, 9), (2.0, 0.0)),   # top
        sample(VALVE, ACCESSORIES, (0, 6), (3.5, 0.0)),   # middle
        sample(VALVE, ACCESSORIES, (0, 3), (5.0, 0.0)),   # bottom
    ])
    assert [p.offset[0] for p in recipe.by_signature[VALVE]] == [2.0, 3.5, 5.0]

    # a target view with the valves at completely different coordinates
    hosts = [host('c', VALVE, ACCESSORIES, (400, 53)),
             host('a', VALVE, ACCESSORIES, (400, 61)),
             host('b', VALVE, ACCESSORIES, (400, 57))]
    placed = dict((a.key, a.placement.offset[0]) for a in layout.assign(hosts, recipe))
    assert placed == {'a': 2.0, 'b': 3.5, 'c': 5.0}, placed


@case
def test_reading_order_is_top_down_then_left_right():
    keys = [(10, 5), (0, 5), (5, 9)]
    assert sorted(keys, key=layout.sort_key) == [(5, 9), (0, 5), (10, 5)]


# --------------------------------------------------------------------------
# replaying
# --------------------------------------------------------------------------

@case
def test_no_spatial_relationship_is_needed():
    """The target view sits 500 ft away and is mirrored - irrelevant here."""
    recipe = layout.learn([sample(PIPE_CW, PIPES, (0, 0), (-2.5, 1.0))])
    hosts = [host(1, PIPE_CW, PIPES, (-4321.0, 987.0))]
    assignment = layout.assign(hosts, recipe)[0]
    assert assignment.placement.offset == (-2.5, 1.0)
    assert assignment.how == layout.EXACT


@case
def test_more_targets_than_the_pattern_cycles():
    """Extra valves keep alternating instead of piling onto the last offset."""
    recipe = layout.learn([
        sample(VALVE, ACCESSORIES, (0, 9), (2.0, 0.0)),
        sample(VALVE, ACCESSORIES, (0, 6), (3.5, 0.0)),
    ])
    hosts = [host(n, VALVE, ACCESSORIES, (0, 100 - n)) for n in range(6)]
    offsets = [a.placement.offset[0]
               for a in sorted(layout.assign(hosts, recipe), key=lambda a: a.rank)]
    assert offsets == [2.0, 3.5, 2.0, 3.5, 2.0, 3.5]


@case
def test_fewer_targets_than_the_pattern():
    recipe = layout.learn([
        sample(VALVE, ACCESSORIES, (0, 9), (2.0, 0.0)),
        sample(VALVE, ACCESSORIES, (0, 6), (3.5, 0.0)),
        sample(VALVE, ACCESSORIES, (0, 3), (5.0, 0.0)),
    ])
    hosts = [host(1, VALVE, ACCESSORIES, (0, 9))]
    assert layout.assign(hosts, recipe)[0].placement.offset[0] == 2.0


@case
def test_unknown_kind_falls_back_to_the_category():
    """A hot water pipe the reference view never tagged still gets a sane spot."""
    recipe = layout.learn([
        sample(PIPE_CW, PIPES, (0, 9), (-2.0, 0.0)),
        sample(PIPE_CW, PIPES, (0, 6), (-4.0, 0.0)),
    ])
    hosts = [host(1, PIPE_HW, PIPES, (0, 0))]
    assignment = layout.assign(hosts, recipe)[0]
    assert assignment.how == layout.CATEGORY
    assert assignment.placement.offset[0] in (-2.0, -4.0)


@case
def test_unknown_category_gets_no_guidance():
    recipe = layout.learn([sample(PIPE_CW, PIPES, (0, 0), (-2.0, 0.0))])
    hosts = [host(1, ('Ducts', 5, 0, 'H'), 'Ducts', (0, 0))]
    assignment = layout.assign(hosts, recipe)[0]
    assert not assignment.is_guided
    assert assignment.how == layout.NONE


@case
def test_category_fallback_picks_a_real_placement():
    """The representative offset must be one a drafter actually chose."""
    recipe = layout.learn([
        sample(PIPE_CW, PIPES, (0, 9), (-2.0, 0.0)),
        sample(PIPE_HW, PIPES, (0, 6), (-2.2, 0.0)),
        sample(('Pipes', 7, 103, 'V'), PIPES, (0, 3), (-20.0, 0.0)),
    ])
    chosen = recipe.by_category[PIPES].offset[0]
    assert chosen in (-2.0, -2.2, -20.0)
    assert chosen != -20.0, 'the outlier must not represent the category'


@case
def test_view_scale_scales_the_offsets():
    recipe = layout.learn([sample(PIPE_CW, PIPES, (0, 0), (-2.0, 1.0),
                                  elbow=(-1.0, 0.5))])
    hosts = [host(1, PIPE_CW, PIPES, (0, 0))]
    assignment = layout.assign(hosts, recipe, scale=2.0)[0]
    assert assignment.placement.offset == (-4.0, 2.0)
    assert assignment.placement.elbow == (-2.0, 1.0)
    # and the recipe itself is not mutated by scaling
    assert recipe.by_signature[PIPE_CW][0].offset == (-2.0, 1.0)


@case
def test_summary_counts_how_each_tag_was_placed():
    recipe = layout.learn([sample(PIPE_CW, PIPES, (0, 0), (-2.0, 0.0))])
    hosts = [host(1, PIPE_CW, PIPES, (0, 0)),
             host(2, PIPE_HW, PIPES, (0, 1)),
             host(3, ('Ducts', 5, 0, 'H'), 'Ducts', (0, 2))]
    counts = layout.summarise(layout.assign(hosts, recipe))
    assert counts == {layout.EXACT: 1, layout.CATEGORY: 1, layout.NONE: 1}


@case
def test_empty_recipe_is_safe():
    recipe = layout.learn([])
    assert recipe.sample_count == 0
    assert recipe.tag_type_for(PIPES) is None
    hosts = [host(1, PIPE_CW, PIPES, (0, 0))]
    assert not layout.assign(hosts, recipe)[0].is_guided


@case
def test_placement_distance_and_repr():
    placement = layout.Placement(TAG_PIPE, (3.0, 4.0))
    assert placement.distance == 5.0
    assert placement.scaled(1.0) is placement
    assert 'Placement' in repr(placement)
