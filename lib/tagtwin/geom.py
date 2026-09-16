# -*- coding: utf-8 -*-
"""Vector helpers and the rigid transform used to line up two views.

Pure Python - no Revit imports - so it can be tested with plain CPython.
Points and vectors are 3-tuples of floats in Revit's internal units (feet).
"""

from __future__ import division

import math

TWO_PI = 2.0 * math.pi


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(v, f):
    return (v[0] * f, v[1] * f, v[2] * f)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def length(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def xy_length(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1])


def distance(a, b):
    return length(sub(a, b))


def normalized(v):
    n = length(v)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def mean_point(points):
    n = len(points)
    if not n:
        return (0.0, 0.0, 0.0)
    sx = sy = sz = 0.0
    for p in points:
        sx += p[0]
        sy += p[1]
        sz += p[2]
    return (sx / n, sy / n, sz / n)


def normalize_angle(angle):
    """Fold an angle into [-pi, pi)."""
    angle = math.fmod(angle, TWO_PI)
    if angle >= math.pi:
        angle -= TWO_PI
    elif angle < -math.pi:
        angle += TWO_PI
    return angle


class Alignment(object):
    """A rigid transform: optional mirror, then rotation about Z, then move.

    ``p' = T + Rz(angle) * M * p`` where ``M`` flips Y when ``mirror`` is set.

    A mirror about *any* vertical plane can be written as a flip about the XZ
    plane followed by a rotation about Z, so this covers every way a repeated
    layout is placed in practice: copied, rotated, or handed (mirrored) - which
    is how back-to-back plumbing suites are usually built.
    """

    __slots__ = ('angle', 'mirror', 'offset', '_cos', '_sin')

    def __init__(self, angle=0.0, mirror=False, offset=(0.0, 0.0, 0.0)):
        self.angle = normalize_angle(float(angle))
        self.mirror = bool(mirror)
        self.offset = (float(offset[0]), float(offset[1]), float(offset[2]))
        self._cos = math.cos(self.angle)
        self._sin = math.sin(self.angle)

    def apply(self, p):
        """Transform a point."""
        x = p[0]
        y = -p[1] if self.mirror else p[1]
        return (x * self._cos - y * self._sin + self.offset[0],
                x * self._sin + y * self._cos + self.offset[1],
                p[2] + self.offset[2])

    def apply_vector(self, v):
        """Transform a direction - same as ``apply`` without the translation."""
        x = v[0]
        y = -v[1] if self.mirror else v[1]
        return (x * self._cos - y * self._sin,
                x * self._sin + y * self._cos,
                v[2])

    @property
    def basis_x(self):
        return (self._cos, self._sin, 0.0)

    @property
    def basis_y(self):
        if self.mirror:
            return (self._sin, -self._cos, 0.0)
        return (-self._sin, self._cos, 0.0)

    @property
    def basis_z(self):
        return (0.0, 0.0, 1.0)

    def inverse(self):
        if self.mirror:
            # (R*M)^-1 = M*R^-1 = R*M  (because M*R(a)*M = R(-a))
            back = Alignment(self.angle, True)
            return Alignment(self.angle, True, scale(back.apply_vector(self.offset), -1.0))
        back = Alignment(-self.angle, False)
        return Alignment(-self.angle, False, scale(back.apply_vector(self.offset), -1.0))

    def is_identity(self, tol=1e-9):
        return (not self.mirror
                and abs(self.angle) < tol
                and length(self.offset) < tol)

    def key(self, ndigits=4):
        """A hashable rounded key, used to drop duplicate hypotheses."""
        return (round(self.angle, ndigits), self.mirror,
                round(self.offset[0], ndigits),
                round(self.offset[1], ndigits),
                round(self.offset[2], ndigits))

    def describe(self, unit='ft'):
        parts = []
        moved = length(self.offset)
        if moved > 1e-6:
            parts.append('moved {0:.2f} {1} ({2:.2f}, {3:.2f}, {4:.2f})'.format(
                moved, unit, self.offset[0], self.offset[1], self.offset[2]))
        degrees = math.degrees(self.angle)
        if abs(degrees) > 1e-4:
            parts.append('rotated {0:.2f} deg'.format(degrees))
        if self.mirror:
            parts.append('mirrored')
        if not parts:
            return 'identical placement (no transform)'
        return ', '.join(parts)

    def __repr__(self):
        return '<Alignment {0}>'.format(self.describe())


IDENTITY = Alignment()


def translation(vector):
    return Alignment(0.0, False, vector)


def alignment_from_points(source, target, mirror=False):
    """Translation-only alignment taking ``source`` onto ``target``."""
    base = Alignment(0.0, mirror)
    return Alignment(0.0, mirror, sub(target, base.apply(source)))


def alignment_from_pairs(s1, t1, s2, t2, mirror=False,
                         length_tolerance=0.02, min_separation=0.5):
    """Derive an alignment from two matched point pairs.

    Returns ``None`` when the pairs cannot describe a rigid transform: the two
    source points are too close together to give a reliable angle, or the
    distances between the pairs disagree (so they are not the same two points).
    """
    v = sub(s2, s1)
    w = sub(t2, t1)
    vxy = xy_length(v)
    wxy = xy_length(w)
    if vxy < min_separation or wxy < min_separation:
        return None
    if abs(vxy - wxy) > length_tolerance:
        return None
    if abs(v[2] - w[2]) > length_tolerance:
        return None
    vy = -v[1] if mirror else v[1]
    angle = math.atan2(w[1], w[0]) - math.atan2(vy, v[0])
    base = Alignment(angle, mirror)
    return Alignment(angle, mirror, sub(t1, base.apply(s1)))


def fit_alignment(pairs, mirror=False):
    """Least squares alignment through matched ``(source, target)`` points.

    Closed form: the best rotation about Z is the argument of the sum of the
    centred source/target vectors multiplied as complex numbers.
    """
    if not pairs:
        return Alignment(0.0, mirror)
    sources = [p[0] for p in pairs]
    targets = [p[1] for p in pairs]
    if mirror:
        sources = [(p[0], -p[1], p[2]) for p in sources]
    cs = mean_point(sources)
    ct = mean_point(targets)
    num = den = 0.0
    for s, t in zip(sources, targets):
        sx = s[0] - cs[0]
        sy = s[1] - cs[1]
        tx = t[0] - ct[0]
        ty = t[1] - ct[1]
        num += sx * ty - sy * tx
        den += sx * tx + sy * ty
    if abs(num) < 1e-12 and abs(den) < 1e-12:
        angle = 0.0
    else:
        angle = math.atan2(num, den)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    offset = (ct[0] - (cs[0] * cos_a - cs[1] * sin_a),
              ct[1] - (cs[0] * sin_a + cs[1] * cos_a),
              ct[2] - cs[2])
    return Alignment(angle, mirror, offset)


def snap_angle(alignment, step_degrees, tolerance_degrees):
    """Snap a fitted angle onto the nearest multiple of ``step_degrees``.

    Real models are drawn on right angles; snapping removes the drift a least
    squares fit picks up from small modelling differences.
    """
    if step_degrees <= 0.0:
        return alignment
    step = math.radians(step_degrees)
    snapped = round(alignment.angle / step) * step
    if abs(normalize_angle(snapped - alignment.angle)) > math.radians(tolerance_degrees):
        return alignment
    return Alignment(snapped, alignment.mirror, alignment.offset)
