# -*- coding: utf-8 -*-
"""Pushing overlapping tags apart.

The failure these come from: tags placed at individually correct offsets piled
into an unreadable knot wherever the pipework converged.
"""

from __future__ import division

from tagtwin import declutter

CASES = []


def case(func):
    CASES.append(func)
    return func


def label(key, x, y, half_width=1.0, half_height=0.25):
    return declutter.Label(key, (x, y), half_width, half_height)


def overlapping_pairs(labels, gap=0.0):
    count = 0
    for i, first in enumerate(labels):
        for second in labels[i + 1:]:
            if declutter.clashes(first, second, gap):
                count += 1
    return count


# --------------------------------------------------------------------------

@case
def test_labels_that_fit_are_left_alone():
    labels = [label(1, 0, 0), label(2, 0, 5), label(3, 0, 10)]
    result = declutter.resolve(labels)
    assert not result.moved
    assert result.iterations <= 1
    assert result.remaining_overlaps == 0


@case
def test_two_stacked_labels_separate():
    labels = [label(1, 0, 0), label(2, 0, 0.1)]
    result = declutter.resolve(labels)
    assert overlapping_pairs(result.labels) == 0
    assert result.remaining_overlaps == 0
    # they part along Y, which is where they overlapped least
    assert abs(labels[0].position[0]) < 0.2 and abs(labels[1].position[0]) < 0.2


@case
def test_a_knot_of_labels_is_fully_separated():
    """Twelve tags dumped on the same spot, as happens where pipes converge."""
    labels = [label(n, 0.05 * n, 0.03 * n) for n in range(12)]
    result = declutter.resolve(labels, gap=0.05, max_shift=20.0)
    assert overlapping_pairs(result.labels, gap=0.05) == 0, result.summary()
    assert result.remaining_overlaps == 0


@case
def test_labels_stay_as_near_their_intended_spot_as_they_can():
    labels = [label(n, 0.0, 0.05 * n) for n in range(6)]
    declutter.resolve(labels, max_shift=10.0)
    # nothing wanders off: the pull keeps the column tight around the original
    assert all(l.distance_moved < 3.0 for l in labels), [l.distance_moved for l in labels]
    # and the one in the middle of the pile moves least in x
    assert all(abs(l.position[0]) < 0.5 for l in labels)


@case
def test_reading_order_is_preserved_in_a_crowded_column():
    """A run of tags must not shuffle - the top one stays on top."""
    labels = [label(n, 0.0, -0.1 * n) for n in range(5)]
    declutter.resolve(labels, gap=0.02, max_shift=20.0)
    heights = [l.position[1] for l in labels]
    assert heights == sorted(heights, reverse=True), heights


@case
def test_max_shift_is_respected():
    labels = [label(n, 0.0, 0.01 * n) for n in range(10)]
    result = declutter.resolve(labels, gap=0.1, max_shift=0.1)
    assert all(l.distance_moved <= 0.1 + 1e-6 for l in result.labels)
    # it cannot fully separate them inside that limit, and says so
    assert result.remaining_overlaps > 0
    assert 'still overlapping' in result.summary()


@case
def test_wide_labels_separate_vertically_not_horizontally():
    """Two long tags overlapping slightly should stack, not shove sideways."""
    labels = [label(1, 0, 0, half_width=3.0, half_height=0.2),
              label(2, 0.5, 0.1, half_width=3.0, half_height=0.2)]
    declutter.resolve(labels, max_shift=10.0)
    assert abs(labels[0].position[1] - labels[1].position[1]) > 0.35
    assert abs(labels[0].position[0]) < 0.5


@case
def test_gap_is_honoured():
    labels = [label(1, 0, 0), label(2, 0, 0.1)]
    declutter.resolve(labels, gap=0.5, max_shift=10.0)
    separation = abs(labels[0].position[1] - labels[1].position[1])
    assert separation >= 0.25 + 0.25 + 0.5 - 1e-6, separation


@case
def test_one_or_no_labels_is_safe():
    assert declutter.resolve([]).summary() == 'no tags to arrange'
    assert declutter.resolve([label(1, 0, 0)]).remaining_overlaps == 0


@case
def test_result_is_deterministic():
    def run():
        labels = [label(n, 0.07 * n, 0.04 * (n % 5)) for n in range(15)]
        declutter.resolve(labels, gap=0.05, max_shift=10.0)
        return [tuple(l.position) for l in labels]
    assert run() == run()


@case
def test_shifts_are_reported_per_label():
    labels = [label(1, 0, 0), label(2, 0, 0.1)]
    result = declutter.resolve(labels, max_shift=10.0)
    shifts = result.shifts()
    assert set(shifts) == {1, 2}
    assert any(abs(s[1]) > 1e-6 for s in shifts.values())


@case
def test_a_big_crowd_stays_quick_and_clean():
    """200 tags in clusters, as a busy riser actually looks."""
    labels = []
    for cluster in range(20):
        for n in range(10):
            labels.append(label(cluster * 10 + n,
                                cluster * 12.0 + 0.05 * n,
                                0.04 * n))
    result = declutter.resolve(labels, gap=0.02, max_shift=20.0)
    assert result.remaining_overlaps == 0, result.summary()
    assert len(result.labels) == 200


@case
def test_an_impossible_crowd_terminates_and_says_so():
    """Given no room to move into, it must stop and report - never spin."""
    labels = [label(n, (n % 20) * 0.3, (n // 20) * 0.1) for n in range(200)]
    result = declutter.resolve(labels, gap=0.02, iterations=40, max_shift=0.2)
    assert result.iterations <= 40
    assert result.remaining_overlaps > 0
    assert 'still overlapping' in result.summary()
    # and nothing was flung beyond the limit while trying
    assert all(l.distance_moved <= 1.0 + 1e-6 for l in result.labels)


@case
def test_touching_exactly_is_not_an_overlap():
    """Labels settle *exactly* the gap apart; that must read as separated."""
    first = label(1, 0.0, 0.0, half_height=0.25)
    second = label(2, 0.0, 0.52)          # 0.25 + 0.25 + 0.02 gap
    assert not declutter.clashes(first, second, 0.02)
    third = label(3, 0.0, 0.50)           # a hair short
    assert declutter.clashes(first, third, 0.02)


@case
def test_the_settled_result_is_the_one_handed_back():
    """Not the state a late pull nudged - that reads as overlapping by a hair."""
    labels = [label(n, 0.0, 0.05 * n) for n in range(8)]
    result = declutter.resolve(labels, gap=0.02, max_shift=20.0)
    assert result.remaining_overlaps == 0
    heights = sorted(l.position[1] for l in labels)
    gaps = [round(b - a, 6) for a, b in zip(heights, heights[1:])]
    assert all(g >= 0.52 - 1e-6 for g in gaps), gaps


@case
def test_a_column_never_reorders_itself():
    """Tags that swap places drag their leaders across each other."""
    labels = [label(n, 0.0, -0.05 * n) for n in range(10)]
    result = declutter.resolve(labels, gap=0.02, max_shift=20.0)
    heights = [l.position[1] for l in labels]
    assert heights == sorted(heights, reverse=True), heights
    assert result.remaining_overlaps == 0


@case
def test_a_row_never_reorders_itself():
    labels = [label(n, 0.3 * n, 0.0, half_width=1.0, half_height=3.0)
              for n in range(8)]
    declutter.resolve(labels, gap=0.02, max_shift=20.0)
    across = [l.position[0] for l in labels]
    assert across == sorted(across), across


@case
def test_order_is_decided_by_intent_not_by_where_they_drifted():
    """Two tags whose intended order is the reverse of their start positions."""
    first = label('top', 0.0, 0.0)
    second = label('below', 0.0, -0.02)
    declutter.resolve([first, second], gap=0.02, max_shift=10.0)
    assert first.position[1] > second.position[1]
