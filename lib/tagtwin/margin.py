# -*- coding: utf-8 -*-
"""Put tags in a clear band beside the drawing, with leaders back to the work.

Placing a tag beside the element it labels is right until the drawing is dense,
and the middle of a riser is nothing but dense. Past a certain crowding there is
no offset that works, because the space simply is not there - which is why a
drafter stops trying and runs the tags down the side of the drawing instead,
leadered back in, leaving the pipework itself clear to read.

This works out the band and which tag belongs in it at what height. It does not
do the stacking: each tag is asked for the height of its own element, and
:mod:`tagtwin.declutter` then packs each column, which keeps leaders short, in
order and uncrossed for free.

Pure Python, no Revit. Coordinates are 2D in the view plane, in feet.
"""

from __future__ import division

LEFT = 'left'
RIGHT = 'right'


class Band(object):
    """Where the tags go: a column down each side of the drawing."""

    __slots__ = ('left', 'right', 'centre', 'bounds')

    def __init__(self, left, right, centre, bounds):
        self.left = left
        self.right = right
        self.centre = centre
        self.bounds = bounds

    def column_for(self, x):
        return LEFT if x < self.centre else RIGHT

    def x_for(self, side):
        return self.left if side == LEFT else self.right

    def __repr__(self):
        return '<Band left={0:.1f} right={1:.1f}>'.format(self.left, self.right)


class Placement(object):
    """One tag's spot in the band."""

    __slots__ = ('key', 'position', 'side', 'anchor')

    def __init__(self, key, position, side, anchor):
        self.key = key
        self.position = position
        self.side = side
        self.anchor = anchor

    @property
    def reach(self):
        """How far the leader has to travel, horizontally."""
        return abs(self.position[0] - self.anchor[0])

    def __repr__(self):
        return '<margin.Placement {0} {1} ({2:.1f}, {3:.1f})>'.format(
            self.key, self.side, self.position[0], self.position[1])


def band_for(points, gutter):
    """The bands to either side of everything in ``points``."""
    if not points:
        return Band(-gutter, gutter, 0.0, (0.0, 0.0))
    xs = [p[0] for p in points]
    low = min(xs)
    high = max(xs)
    return Band(low - gutter, high + gutter, (low + high) / 2.0, (low, high))


def plan(entries, gutter, band=None):
    """Work out where each tag goes in the band.

    ``entries`` are ``(key, x, y)`` for the elements being tagged. Each tag is
    sent to the nearer side at its own element's height, so the leader is a
    short horizontal run rather than a diagonal across the drawing.
    """
    points = [(x, y) for _, x, y in entries]
    if band is None:
        band = band_for(points, gutter)
    placements = []
    for key, x, y in entries:
        side = band.column_for(x)
        placements.append(Placement(key, (band.x_for(side), y), side, (x, y)))
    return band, placements


def summarise(placements):
    """``{side: count}`` for the report."""
    counts = {}
    for placement in placements:
        counts[placement.side] = counts.get(placement.side, 0) + 1
    return counts
