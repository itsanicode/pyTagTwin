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
    placement = layout.assign(hosts, recipe)[0].placement
    assert placement.offset_in_view(scale=2.0) == (-4.0, 2.0)
    assert placement.elbow_in_view(2.0) == (-2.0, 1.0)
    # the recipe itself is never mutated by scaling
    assert placement.offset == (-2.0, 1.0)


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
    assert placement.offset_in_view() == (3.0, 4.0)
    assert 'Placement' in repr(placement)


# --------------------------------------------------------------------------
# host-relative placement: the fault that scattered tags across the sheet
# --------------------------------------------------------------------------

def host_placement(along, across, tag_type=TAG_PIPE, elbow=None):
    return layout.Placement(tag_type, elbow=elbow, frame=layout.HOST_FRAME,
                            along=along, across=across)


UP = (0.0, 1.0)
ACROSS_RIGHT = (1.0, 0.0)


@case
def test_a_tag_follows_the_length_of_the_pipe_it_labels():
    """The whole point: a short branch must not inherit a long riser's reach.

    Tagged a quarter of the way up a 20 ft riser, the tag sits 5 ft above its
    midpoint. Read as a plain offset, a 4 ft branch would put its tag 5 ft
    above *its* midpoint - 3 ft past the end of the pipe, floating in space.
    """
    placement = host_placement(along=0.25, across=-2.0)
    on_riser = placement.offset_in_view(UP, 20.0)
    on_branch = placement.offset_in_view(UP, 4.0)
    assert abs(on_riser[1] - 5.0) < 1e-9
    assert abs(on_branch[1] - 1.0) < 1e-9, on_branch
    # and both sit the same distance out to the side
    assert abs(on_riser[0] - 2.0) < 1e-9 and abs(on_branch[0] - 2.0) < 1e-9


@case
def test_the_sideways_offset_follows_the_view_scale_not_the_pipe():
    """Along is a fraction of the host; across is a distance on the drawing."""
    placement = host_placement(along=0.5, across=-2.0)
    offset = placement.offset_in_view(UP, 10.0, scale=2.0)
    assert abs(offset[1] - 5.0) < 1e-9, 'along must not scale with the view'
    assert abs(offset[0] - 4.0) < 1e-9, 'across must scale with the view'


@case
def test_a_tag_turns_with_its_pipe():
    """The same placement on a horizontal pipe puts the tag above it."""
    placement = host_placement(along=0.0, across=-2.0)
    on_vertical = placement.offset_in_view(UP, 10.0)
    on_horizontal = placement.offset_in_view(ACROSS_RIGHT, 10.0)
    assert abs(on_vertical[0] - 2.0) < 1e-9 and abs(on_vertical[1]) < 1e-9
    assert abs(on_horizontal[1] + 2.0) < 1e-9 and abs(on_horizontal[0]) < 1e-9


@case
def test_learning_and_replaying_a_host_offset_round_trips():
    offset = (-2.5, 4.0)
    axis, length = UP, 16.0
    along, across = layout.host_frame_offset(offset, axis, length)
    back = layout.Placement(TAG_PIPE, frame=layout.HOST_FRAME,
                            along=along, across=across).offset_in_view(axis, length)
    assert abs(back[0] - offset[0]) < 1e-9 and abs(back[1] - offset[1]) < 1e-9


@case
def test_an_element_with_no_direction_keeps_a_plain_offset():
    """Fixtures and valves have no axis, so they keep a right/up offset."""
    placement = layout.Placement(TAG_VALVE, (1.5, 0.5))
    assert placement.frame == layout.VIEW_FRAME
    assert placement.offset_in_view(None, 0.0) == (1.5, 0.5)
    # and a host-framed placement falls back too when the pipe points at us
    edge_on = host_placement(along=0.5, across=-2.0)
    assert edge_on.offset_in_view(None, 0.0) == (0.0, 0.0)


@case
def test_host_frame_offset_is_safe_on_a_zero_length_host():
    assert layout.host_frame_offset((1.0, 2.0), UP, 0.0) == (0.0, 0.0)


# --------------------------------------------------------------------------
# tagging density - how many of a kind the reference view actually tagged
# --------------------------------------------------------------------------

@case
def test_density_copies_how_much_the_reference_tagged():
    """Tagging every pipe when the reference tagged three is what made a mess."""
    recipe = layout.learn(
        [sample(PIPE_CW, PIPES, (0, 9), (-2.0, 0.0)),
         sample(PIPE_CW, PIPES, (0, 6), (-3.0, 0.0)),
         sample(PIPE_CW, PIPES, (0, 3), (-4.0, 0.0))],
        population={PIPE_CW: 30})
    assert abs(recipe.density(PIPE_CW) - 0.1) < 1e-9
    assert recipe.tags_wanted(PIPE_CW, 30) == 3
    assert recipe.tags_wanted(PIPE_CW, 60) == 6


@case
def test_everything_tagged_stays_everything_tagged():
    recipe = layout.learn(
        [sample(VALVE, ACCESSORIES, (0, 9), (2.0, 0.0)),
         sample(VALVE, ACCESSORIES, (0, 6), (2.0, 0.0))],
        population={VALVE: 2})
    assert recipe.density(VALVE) == 1.0
    assert recipe.tags_wanted(VALVE, 7) == 7


@case
def test_at_least_one_is_tagged_when_the_reference_tagged_any():
    recipe = layout.learn([sample(PIPE_CW, PIPES, (0, 0), (-2.0, 0.0))],
                          population={PIPE_CW: 100})
    assert recipe.tags_wanted(PIPE_CW, 3) == 1


@case
def test_untagged_kinds_are_never_tagged():
    """The category fallback positions an existing tag; it never creates one."""
    recipe = layout.learn([sample(PIPE_CW, PIPES, (0, 0), (-2.0, 0.0))],
                          population={PIPE_CW: 4, PIPE_HW: 9})
    assert recipe.tags_wanted(PIPE_HW, 9) == 0
    # but if one is already there, it still gets positioned
    hosts = [host(1, PIPE_HW, PIPES, (0, 0))]
    assert layout.assign(hosts, recipe)[0].how == layout.CATEGORY


@case
def test_population_defaults_to_what_was_tagged():
    recipe = layout.learn([sample(PIPE_CW, PIPES, (0, 0), (-2.0, 0.0))])
    assert recipe.density(PIPE_CW) == 1.0


@case
def test_tagged_kinds_reports_busiest_first():
    recipe = layout.learn(
        [sample(PIPE_CW, PIPES, (0, 9), (-2.0, 0.0)),
         sample(PIPE_CW, PIPES, (0, 6), (-3.0, 0.0)),
         sample(VALVE, ACCESSORIES, (0, 3), (2.0, 0.0))],
        population={PIPE_CW: 20, VALVE: 2})
    rows = recipe.tagged_kinds()
    assert rows[0][0] == PIPE_CW and rows[0][1] == 2 and rows[0][2] == 20
    assert rows[1][0] == VALVE
