# -*- coding: utf-8 -*-
"""A synthetic plumbing suite, shaped like the riser diagrams this tool targets.

Vertical CW/HW risers, horizontal branches off them, valves and fixtures - the
mix of repeated identical parts and a few unique ones that makes matching both
possible and interesting.
"""

from __future__ import division

from tagtwin.geom import Alignment
from tagtwin.signature import (ElementRecord, HORIZONTAL, POINT, VERTICAL,
                               classify_direction)

CW = 101          # cold water system
HW = 102          # hot water system
PIPE = 'Pipes'
FITTING = 'Pipe Fittings'
FIXTURE = 'Plumbing Fixtures'
ACCESSORY = 'Pipe Accessories'


def _pipe(key, start, end, system, diameter):
    axis = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    llength = (axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2) ** 0.5
    midpoint = ((start[0] + end[0]) / 2.0,
                (start[1] + end[1]) / 2.0,
                (start[2] + end[2]) / 2.0)
    return ElementRecord(key=key, category=PIPE, type_id=1, point=midpoint,
                         system_id=system, size=(round(diameter, 4),),
                         length=round(llength, 2),
                         orientation=classify_direction(axis), axis=axis,
                         label='Pipe {0}"'.format(diameter * 12))


def _point_element(key, category, type_id, point, system=0, label=''):
    return ElementRecord(key=key, category=category, type_id=type_id, point=point,
                         system_id=system, size=None, length=None,
                         orientation=POINT, label=label or category)


def build_suite(start_key=1000):
    """One plumbing suite: two risers, four branches, three fixtures, valves."""
    key = [start_key]

    def next_key():
        key[0] += 1
        return key[0]

    records = []
    # two vertical risers, cold and hot, 12 ft apart
    records.append(_pipe(next_key(), (0.0, 0.0, 0.0), (0.0, 0.0, 10.0), CW, 0.1667))
    records.append(_pipe(next_key(), (12.0, 0.0, 0.0), (12.0, 0.0, 10.0), HW, 0.125))
    # horizontal branches off each riser at two heights
    records.append(_pipe(next_key(), (0.0, 0.0, 8.0), (4.0, 0.0, 8.0), CW, 0.1042))
    records.append(_pipe(next_key(), (0.0, 0.0, 4.0), (4.0, 0.0, 4.0), CW, 0.1042))
    records.append(_pipe(next_key(), (12.0, 0.0, 8.0), (8.0, 0.0, 8.0), HW, 0.1042))
    records.append(_pipe(next_key(), (12.0, 0.0, 4.0), (8.0, 0.0, 4.0), HW, 0.1042))
    # legs turning out of the riser plane, then drops to the fixtures
    records.append(_pipe(next_key(), (4.0, 0.0, 8.0), (4.0, 3.0, 8.0), CW, 0.0833))
    records.append(_pipe(next_key(), (8.0, 0.0, 8.0), (8.0, 3.0, 8.0), HW, 0.0833))
    records.append(_pipe(next_key(), (4.0, 3.0, 8.0), (4.0, 3.0, 2.5), CW, 0.0625))
    records.append(_pipe(next_key(), (8.0, 3.0, 8.0), (8.0, 3.0, 2.5), HW, 0.0625))
    # elbows where the branches turn
    for point in [(0.0, 0.0, 8.0), (0.0, 0.0, 4.0), (12.0, 0.0, 8.0), (12.0, 0.0, 4.0)]:
        records.append(_point_element(next_key(), FITTING, 21, point, CW, 'Elbow'))
    # shutoff valves - identical to each other, only position tells them apart
    records.append(_point_element(next_key(), ACCESSORY, 31, (2.0, 0.0, 8.0), CW, 'Shutoff'))
    records.append(_point_element(next_key(), ACCESSORY, 31, (2.0, 0.0, 4.0), CW, 'Shutoff'))
    records.append(_point_element(next_key(), ACCESSORY, 31, (10.0, 0.0, 8.0), HW, 'Shutoff'))
    # fixtures - each a distinct type, the best anchors in the set
    records.append(_point_element(next_key(), FIXTURE, 41, (4.0, 3.5, 2.5), 0, 'WC-1A'))
    records.append(_point_element(next_key(), FIXTURE, 42, (8.0, 3.5, 2.5), 0, 'LAV-1'))
    records.append(_point_element(next_key(), FIXTURE, 43, (6.0, 5.0, 3.0), 0, 'SH-1A'))
    return records


def transformed_suite(alignment, start_key=2000, jitter=0.0, drop_keys=(),
                      extra=0):
    """The same suite moved by ``alignment``, as a second set of elements.

    ``jitter`` nudges every point (modelling slop), ``drop_keys`` removes
    elements by their 1-based index, ``extra`` appends unrelated elements.
    """
    source = build_suite(start_key=0)
    records = []
    offsets = _jitter_sequence(jitter, len(source) * 3)
    index = 0
    for position, record in enumerate(source, start=1):
        if position in drop_keys:
            index += 3
            continue
        point = alignment.apply(record.point)
        point = (point[0] + offsets[index],
                 point[1] + offsets[index + 1],
                 point[2] + offsets[index + 2])
        index += 3
        axis = alignment.apply_vector(record.axis) if record.axis else None
        records.append(ElementRecord(
            key=start_key + position, category=record.category,
            type_id=record.type_id, point=point, system_id=record.system_id,
            size=record.size, length=record.length,
            orientation=record.orientation, axis=axis, label=record.label))
    for n in range(extra):
        records.append(_point_element(start_key + 900 + n, FIXTURE, 99,
                                      (100.0 + n * 3.0, 50.0, 0.0), 0, 'Unrelated'))
    return records


def _jitter_sequence(amount, count):
    """Deterministic pseudo-random offsets - no seeding, no surprises in CI."""
    if amount <= 0.0:
        return [0.0] * count
    values = []
    state = 12345
    for _ in range(count):
        state = (1103515245 * state + 12345) % 2147483648
        values.append(((state / 2147483648.0) * 2.0 - 1.0) * amount)
    return values


SUITE_SIZE = len(build_suite())
