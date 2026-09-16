# -*- coding: utf-8 -*-
"""A signature-aware spatial hash.

Matching asks the same question thousands of times - *is there an element with
this signature within tolerance of this point* - so the answer has to be O(1).
Points are bucketed by ``(signature, cell)`` with a cell size of one tolerance,
which puts every hit in the 27 cells around the query.
"""

from __future__ import division

import math


class PointIndex(object):

    def __init__(self, records, level, cell_size):
        self.level = level
        self.cell_size = max(float(cell_size), 1e-9)
        self._buckets = {}
        for record in records:
            self._buckets.setdefault(self._key(record.signature(level), record.point),
                                     []).append(record)

    def _cell(self, point):
        c = self.cell_size
        return (int(math.floor(point[0] / c)),
                int(math.floor(point[1] / c)),
                int(math.floor(point[2] / c)))

    def _key(self, signature, point):
        cell = self._cell(point)
        return (signature, cell[0], cell[1], cell[2])

    def query(self, signature, point, tolerance):
        """Records with ``signature`` within ``tolerance`` of ``point``.

        Returns ``[(distance, record), ...]`` sorted by distance.
        """
        cx, cy, cz = self._cell(point)
        found = []
        tol_sq = tolerance * tolerance
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    bucket = self._buckets.get((signature, cx + dx, cy + dy, cz + dz))
                    if not bucket:
                        continue
                    for record in bucket:
                        p = record.point
                        ex = p[0] - point[0]
                        ey = p[1] - point[1]
                        ez = p[2] - point[2]
                        dist_sq = ex * ex + ey * ey + ez * ez
                        if dist_sq <= tol_sq:
                            found.append((math.sqrt(dist_sq), record))
        found.sort(key=lambda item: (item[0], item[1].key))
        return found

    def nearest(self, signature, point, tolerance):
        hits = self.query(signature, point, tolerance)
        return hits[0] if hits else None
