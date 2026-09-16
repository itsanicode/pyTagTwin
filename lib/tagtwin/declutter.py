# -*- coding: utf-8 -*-
"""Push overlapping tags apart without losing the arrangement they came from.

Placing every tag at the offset the reference view used is only right until two
of them want the same piece of paper. Where pipework converges the tags pile
into an unreadable knot, which no amount of better offsets fixes - the offsets
are individually correct.

Every label starts where the reference view put it. Those that collide are
gathered into runs and each run is laid out in order along its short axis,
centred on the average of where its members wanted to be. Laying a run out can
push it into its neighbours, so the next pass finds one bigger run; a handful of
passes settles a whole view. A label with room to spare never moves at all.

Two details that matter for a drawing rather than a map:

* A clashing run is laid out **as a run** - in order, evenly spaced, centred on
  where its members wanted to be - rather than nudged apart a pair at a time.
  Nudging expands a stack from the ends inward, one slot per pass, so twenty
  tags need hundreds of passes; laying the run out is exact and immediate.
* Labels keep the order their elements are in. Tags that swap places drag their
  leaders across each other, which is most of what a cluttered drawing is.
* A label is never allowed to drift further than ``max_shift`` from its
  intended spot. Past that it is better to leave a tag overlapping - and say
  so - than to strand it somewhere it no longer reads as belonging to its pipe.

Pure Python, no Revit. Coordinates are 2D in the view plane, in feet.
"""

from __future__ import division

import math


class Label(object):
    """One tag: where it wants to be, and how big it is."""

    __slots__ = ('key', 'desired', 'half_width', 'half_height', 'anchor',
                 'position')

    def __init__(self, key, desired, half_width, half_height, anchor=None):
        self.key = key
        self.desired = (float(desired[0]), float(desired[1]))
        self.half_width = float(half_width)
        self.half_height = float(half_height)
        self.anchor = anchor
        self.position = list(self.desired)

    @property
    def shift(self):
        return (self.position[0] - self.desired[0],
                self.position[1] - self.desired[1])

    @property
    def distance_moved(self):
        dx, dy = self.shift
        return math.sqrt(dx * dx + dy * dy)

    def __repr__(self):
        return '<Label {0} ({1:.2f}, {2:.2f})>'.format(
            self.key, self.position[0], self.position[1])


class Result(object):
    """What the solver managed."""

    def __init__(self, labels, iterations, remaining_overlaps):
        self.labels = labels
        self.iterations = iterations
        self.remaining_overlaps = remaining_overlaps

    @property
    def moved(self):
        return [l for l in self.labels if l.distance_moved > 1e-9]

    def shifts(self):
        return dict((l.key, l.shift) for l in self.labels)

    def summary(self):
        if not self.labels:
            return 'no tags to arrange'
        text = '{0} of {1} tag(s) nudged apart in {2} pass(es)'.format(
            len(self.moved), len(self.labels), self.iterations)
        if self.remaining_overlaps:
            text += ', {0} still overlapping'.format(self.remaining_overlaps)
        return text


#: boxes this close count as separated. Labels settle *exactly* gap apart, so
#: without a tolerance the final touch reads as a clash and the solver never
#: reports itself finished.
TOUCHING = 1e-6


def clashes(first, second, gap):
    """Whether two boxes genuinely overlap, rather than merely touching."""
    x_overlap, y_overlap = _overlap(first, second, gap)
    return x_overlap > TOUCHING and y_overlap > TOUCHING


def _overlap(first, second, gap):
    """``(x overlap, y overlap)``, both positive only when the boxes clash."""
    dx = abs(first.position[0] - second.position[0])
    dy = abs(first.position[1] - second.position[1])
    x_overlap = (first.half_width + second.half_width + gap) - dx
    y_overlap = (first.half_height + second.half_height + gap) - dy
    return x_overlap, y_overlap


class _Grid(object):
    """Buckets labels so each pass looks at neighbours, not at everything."""

    def __init__(self, labels, cell):
        self.cell = max(cell, 1e-6)
        self.buckets = {}
        for label in labels:
            self.buckets.setdefault(self._key(label), []).append(label)

    def _key(self, label):
        return (int(math.floor(label.position[0] / self.cell)),
                int(math.floor(label.position[1] / self.cell)))

    def neighbours(self, label):
        cx, cy = self._key(label)
        found = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                found.extend(self.buckets.get((cx + dx, cy + dy), ()))
        return found


def _half(label, axis):
    return label.half_height if axis else label.half_width


def _clash_groups(ordered, cell, gap):
    """Labels joined into groups by who overlaps whom."""
    grid = _Grid(ordered, cell)
    neighbours = {}
    for label in ordered:
        for other in grid.neighbours(label):
            if other is label or not clashes(label, other, gap):
                continue
            neighbours.setdefault(id(label), []).append(other)

    groups = []
    visited = set()
    for label in ordered:
        if id(label) in visited or id(label) not in neighbours:
            continue
        stack = [label]
        group = []
        visited.add(id(label))
        while stack:
            current = stack.pop()
            group.append(current)
            for other in neighbours.get(id(current), ()):
                if id(other) not in visited:
                    visited.add(id(other))
                    stack.append(other)
        if len(group) > 1:
            groups.append(group)
    return groups


def _pack(group, gap):
    """Lay a clashing group out in one go, in order, along its short axis.

    Nudging a stack apart a pair at a time expands it from the ends inward, one
    slot per pass, so a run of twenty tags needs hundreds of passes to come
    clear. Solving the run as a run instead is exact and immediate - and since
    tags are wide and short, stacking them vertically is both what fits and
    what a drafter would do.
    """
    average_width = sum(l.half_width for l in group) / float(len(group))
    average_height = sum(l.half_height for l in group) / float(len(group))
    axis = 1 if average_height <= average_width else 0
    movable = sorted(group, key=lambda l: (l.desired[axis], repr(l.key)))

    extent = sum(2.0 * _half(l, axis) for l in movable) + gap * (len(movable) - 1)
    centre = sum(l.desired[axis] for l in movable) / float(len(movable))
    cursor = centre - extent / 2.0
    for label in movable:
        half = _half(label, axis)
        label.position[axis] = cursor + half
        label.position[1 - axis] = label.desired[1 - axis]
        cursor += 2.0 * half + gap


def resolve(labels, gap=0.0, iterations=60, max_shift=None):
    """Separate overlapping labels, keeping them near where they wanted to be.

    Each run of labels that clash is laid out as a run: in intended order,
    spaced by ``gap``, centred on the average of where its members wanted to
    be. Packing a run can push it into its neighbours, which merges them into
    one bigger run on the next pass, and a few passes settle the whole view.

    ``max_shift`` bounds how far a label may end up from its intended offset.
    It is applied at the end rather than during, because clamping a packed run
    mid-flight just re-creates the overlap it was packed to remove; where the
    limit does bite, the labels left overlapping are reported instead.
    """
    labels = list(labels)
    if len(labels) < 2:
        return Result(labels, 0, 0)

    for label in labels:
        label.position = list(label.desired)

    biggest = max(max(l.half_width, l.half_height) for l in labels)
    cell = max(biggest * 2.0 + gap, 1e-6)
    ordered = sorted(labels, key=lambda l: (l.desired[1], l.desired[0], repr(l.key)))

    passes = 0
    for passes in range(1, max(1, int(iterations)) + 1):
        groups = _clash_groups(ordered, cell, gap)
        if not groups:
            break
        for group in groups:
            _pack(group, gap)

    if max_shift is not None:
        for label in ordered:
            _clamp(label, max_shift)

    return Result(labels, passes, _count_clashes(ordered, cell, gap))


def _count_clashes(ordered, cell, gap):
    grid = _Grid(ordered, cell)
    seen = set()
    total = 0
    for label in ordered:
        for other in grid.neighbours(label):
            if other is label:
                continue
            pair = (id(label), id(other))
            if pair in seen or (pair[1], pair[0]) in seen:
                continue
            seen.add(pair)
            if clashes(label, other, gap):
                total += 1
    return total


def _clamp(label, max_shift):
    dx, dy = label.shift
    distance = math.sqrt(dx * dx + dy * dy)
    if distance <= max_shift or distance < 1e-12:
        return
    factor = max_shift / distance
    label.position[0] = label.desired[0] + dx * factor
    label.position[1] = label.desired[1] + dy * factor
