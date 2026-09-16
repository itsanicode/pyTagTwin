# -*- coding: utf-8 -*-
"""Element fingerprints - what makes two elements "the same element".

A signature has to be **invariant under the transform between the two views**,
otherwise the same fitting that finds the transform could never use it. So a
signature never contains an absolute position or an absolute direction. What it
does contain is what a drafter would look at: category, type, system, size,
length and whether the element runs up or along.

Three levels are tried in turn, so a run degrades gracefully instead of failing
outright when the second layout was modelled slightly differently:

=========  ==========================================================
STRICT     category, type, system, size and length, orientation
MEDIUM     category, type, system, orientation  (lengths/sizes differ)
LOOSE      category and type only
=========  ==========================================================
"""

from __future__ import division

STRICT = 0
MEDIUM = 1
LOOSE = 2

LEVEL_NAMES = {STRICT: 'exact', MEDIUM: 'same type + system', LOOSE: 'same type'}

#: orientation classes - invariant under rotation about Z and mirroring
VERTICAL = 'V'
HORIZONTAL = 'H'
SLOPED = 'S'
POINT = 'P'


def quantize(value, quantum):
    """Round ``value`` onto a grid of ``quantum`` so near-equal sizes agree."""
    if value is None:
        return None
    if quantum <= 0.0:
        return float(value)
    return round(float(value) / quantum) * quantum


def classify_direction(axis, vertical_tolerance=0.02):
    """Bucket a direction as vertical, horizontal or sloped."""
    if axis is None:
        return POINT
    dz = abs(axis[2])
    norm = (axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2) ** 0.5
    if norm < 1e-9:
        return POINT
    dz /= norm
    if dz > 1.0 - vertical_tolerance:
        return VERTICAL
    if dz < vertical_tolerance:
        return HORIZONTAL
    return SLOPED


class ElementRecord(object):
    """One model element, reduced to what matching needs."""

    __slots__ = ('key', 'category', 'type_id', 'system_id', 'size',
                 'length', 'orientation', 'point', 'axis', 'label')

    def __init__(self, key, category, type_id, point,
                 system_id=0, size=None, length=None, orientation=POINT,
                 axis=None, label=''):
        self.key = key
        self.category = category
        self.type_id = type_id
        self.system_id = system_id
        self.size = size
        self.length = length
        self.orientation = orientation
        self.point = (float(point[0]), float(point[1]), float(point[2]))
        self.axis = axis
        self.label = label

    def signature(self, level=STRICT):
        if level == LOOSE:
            return (self.category, self.type_id)
        if level == MEDIUM:
            return (self.category, self.type_id, self.system_id, self.orientation)
        return (self.category, self.type_id, self.system_id,
                self.orientation, self.size, self.length)

    def __repr__(self):
        return '<ElementRecord {0} {1}>'.format(self.key, self.label or self.category)


def group_by_signature(records, level=STRICT):
    """``{signature: [record, ...]}``."""
    groups = {}
    for record in records:
        groups.setdefault(record.signature(level), []).append(record)
    return groups


def rarity_sorted_signatures(source_groups, target_groups):
    """Signatures present on both sides, rarest first.

    Rare signatures make the best anchors: the fewer candidates a signature has,
    the fewer wrong hypotheses it can produce.
    """
    common = [s for s in source_groups if s in target_groups]
    common.sort(key=lambda s: (min(len(source_groups[s]), len(target_groups[s])),
                               len(source_groups[s]) * len(target_groups[s]),
                               repr(s)))
    return common


def identical_in(records, reference, level=STRICT):
    """Every record sharing ``reference``'s signature (``reference`` included)."""
    wanted = reference.signature(level)
    return [r for r in records if r.signature(level) == wanted]
