# -*- coding: utf-8 -*-
"""Pair up the elements of two views, one to one.

:mod:`tagtwin.align` produces a transform; this module turns it into an actual
element-to-element map, which is what the annotations are re-hosted onto.

Two things make the map better than "nearest neighbour":

* **Cascading signature levels.** Every element is first matched on its exact
  signature. Whatever is left over is retried on looser ones, so a pipe cut
  half an inch shorter in the second suite still finds its twin instead of
  being dropped.
* **Refinement.** Once there is a map, the transform is re-fitted through all
  matched pairs (least squares) and everything is matched again. That pulls in
  elements the initial two-point hypothesis just missed, the same way ICP
  tightens a point-cloud registration.
"""

from __future__ import division

from tagtwin import align
from tagtwin import geom
from tagtwin import signature as sig
from tagtwin.spatial import PointIndex


class Match(object):
    """One matched pair."""

    __slots__ = ('source', 'target', 'level', 'distance', 'ambiguous')

    def __init__(self, source, target, level, distance, ambiguous=False):
        self.source = source
        self.target = target
        self.level = level
        self.distance = distance
        self.ambiguous = ambiguous

    @property
    def is_exact(self):
        return self.level == sig.STRICT

    def __repr__(self):
        return '<Match {0} -> {1} ({2}, {3:.4f})>'.format(
            self.source.key, self.target.key, sig.LEVEL_NAMES[self.level], self.distance)


class MatchResult(object):

    def __init__(self, alignment, matches, unmatched_source, unmatched_target):
        self.alignment = alignment
        self.matches = matches
        self.unmatched_source = unmatched_source
        self.unmatched_target = unmatched_target

    @property
    def id_map(self):
        """``{source key: target key}`` - what re-hosting runs on."""
        return dict((m.source.key, m.target.key) for m in self.matches)

    @property
    def match_map(self):
        return dict((m.source.key, m) for m in self.matches)

    @property
    def source_count(self):
        return len(self.matches) + len(self.unmatched_source)

    @property
    def coverage(self):
        total = self.source_count
        if not total:
            return 0.0
        return len(self.matches) / float(total)

    @property
    def exact_count(self):
        return sum(1 for m in self.matches if m.is_exact)

    @property
    def ambiguous_count(self):
        return sum(1 for m in self.matches if m.ambiguous)

    @property
    def total_distance(self):
        return sum(m.distance for m in self.matches)

    def quality(self):
        """A ranking key: more matches first, then exactness, then tightness."""
        return (len(self.matches), self.exact_count, -self.total_distance)

    def __repr__(self):
        return '<MatchResult {0}/{1} matched ({2:.0%})>'.format(
            len(self.matches), self.source_count, self.coverage)


def match_elements(source_records, target_records, alignment, options):
    """Greedy one-to-one assignment under ``alignment``.

    Candidate pairs are collected per signature level and assigned shortest
    first, so a close pair is never stolen by a distant one. Ties - a second
    candidate just as close - are flagged rather than silently resolved.
    """
    matches = []
    taken_targets = set()
    remaining = list(source_records)

    for level in options.levels:
        if not remaining:
            break
        tolerance = options.tolerance_for(level)
        available = [r for r in target_records if r.key not in taken_targets]
        if not available:
            break
        index = PointIndex(available, level, tolerance)

        candidates = []
        ambiguous_sources = set()
        for record in remaining:
            hits = index.query(record.signature(level),
                               alignment.apply(record.point), tolerance)
            if len(hits) > 1 and abs(hits[0][0] - hits[1][0]) < tolerance * 0.5:
                ambiguous_sources.add(record.key)
            for distance, target in hits:
                candidates.append((distance, record.key, target.key, record, target))

        candidates.sort(key=lambda c: (c[0], c[1], c[2]))
        matched_sources = set()
        for distance, source_key, target_key, record, target in candidates:
            if source_key in matched_sources or target_key in taken_targets:
                continue
            matched_sources.add(source_key)
            taken_targets.add(target_key)
            matches.append(Match(record, target, level, distance,
                                 ambiguous=source_key in ambiguous_sources))

        remaining = [r for r in remaining if r.key not in matched_sources]

    unmatched_target = [r for r in target_records if r.key not in taken_targets]
    return MatchResult(alignment, matches, remaining, unmatched_target)


def refine_alignment(match_result, options):
    """Re-fit the transform through every matched pair."""
    pairs = [(m.source.point, m.target.point) for m in match_result.matches]
    if len(pairs) < 2:
        return match_result.alignment
    fitted = geom.fit_alignment(pairs, match_result.alignment.mirror)
    if options.snap_angle_degrees > 0.0:
        fitted = geom.snap_angle(fitted, options.snap_angle_degrees,
                                 options.snap_angle_tolerance)
    return fitted


class SolveResult(object):
    """What a full solve produced, plus everything the report wants to show."""

    def __init__(self, alignment_result, match_result, iterations):
        self.alignment_result = alignment_result
        self.match_result = match_result
        self.iterations = iterations

    @property
    def alignment(self):
        return self.match_result.alignment

    @property
    def coverage(self):
        return self.match_result.coverage

    @property
    def id_map(self):
        return self.match_result.id_map

    def confidence(self):
        """A 0.0 - 1.0 score for "are these two views really the same thing".

        Coverage is the bulk of it, discounted when matches needed relaxed
        signatures or when a rival transform scored as well as the winner.

        This is a description, not a verdict on whether to run: a view full of
        untagged pipework scores low while still carrying every tag across.
        Use :class:`tagtwin.outlook.AnnotationOutlook` to decide that.
        """
        result = self.match_result
        if not result.matches:
            return 0.0
        count = float(len(result.matches))
        # One combined discount rather than three multiplied together - stacking
        # them dragged an otherwise good match down into "poor" territory.
        penalty = 0.15 * (1.0 - result.exact_count / count)
        penalty += 0.20 * (result.ambiguous_count / count)
        if not self.alignment_result.is_unambiguous:
            penalty += 0.10
        score = result.coverage * max(0.55, 1.0 - penalty)
        return max(0.0, min(1.0, score))

    def verdict(self):
        confidence = self.confidence()
        if confidence >= 0.9:
            return 'excellent'
        if confidence >= 0.7:
            return 'good'
        if confidence >= 0.4:
            return 'partial'
        return 'poor'


def solve(source_records, target_records, options, seed=None):
    """Find the transform between two element sets and pair them up."""
    alignment_result = align.find_alignment(source_records, target_records,
                                            options, seed=seed)
    result = match_elements(source_records, target_records,
                            alignment_result.alignment, options)
    iterations = 0
    for _ in range(max(0, options.refine_iterations)):
        refined = refine_alignment(result, options)
        if refined.key() == result.alignment.key():
            break
        candidate = match_elements(source_records, target_records, refined, options)
        if candidate.quality() <= result.quality():
            break
        result = candidate
        iterations += 1
    return SolveResult(alignment_result, result, iterations)
