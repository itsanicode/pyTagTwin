# -*- coding: utf-8 -*-
"""Find the transform that lays one view's elements over another's.

Nothing here knows about Revit. The input is two lists of
:class:`tagtwin.signature.ElementRecord`; the output is the
:class:`tagtwin.geom.Alignment` that best carries the source elements onto the
target ones.

The search is a small RANSAC:

1. Generate hypotheses from **anchor pairs** - elements whose signature is rare
   enough to be nearly unambiguous. A single pair gives a translation; two pairs
   give a rotation (and, tried separately, a mirrored rotation).
2. Score every hypothesis by how many source elements land on a target element
   of the same signature, breaking ties on total distance. Scoring runs against
   a stratified *sample* of the source elements, because ranking thousands of
   hypotheses against every element of a large view is the one part of this
   that gets genuinely slow on IronPython.
3. Re-score the handful of finalists against every element, and keep the best.
   A hypothesis that is perfect on the whole view ends the search early.

Scoring does not enforce a one-to-one assignment - :mod:`tagtwin.matching` does
that once, on the winner - because an approximate score is enough to rank
hypotheses and is much cheaper.
"""

from __future__ import division

from tagtwin import geom
from tagtwin import signature as sig
from tagtwin.spatial import PointIndex


class AlignmentResult(object):

    __slots__ = ('alignment', 'hits', 'total_distance', 'source_count',
                 'target_count', 'hypotheses_tested', 'runner_up_hits')

    def __init__(self, alignment, hits, total_distance, source_count,
                 target_count, hypotheses_tested=0, runner_up_hits=0):
        self.alignment = alignment
        self.hits = hits
        self.total_distance = total_distance
        self.source_count = source_count
        self.target_count = target_count
        self.hypotheses_tested = hypotheses_tested
        self.runner_up_hits = runner_up_hits

    @property
    def coverage(self):
        """Share of source elements the transform explains, 0.0 - 1.0."""
        if not self.source_count:
            return 0.0
        return self.hits / float(self.source_count)

    @property
    def is_unambiguous(self):
        """True when no rival hypothesis came close to the winner."""
        if not self.hits:
            return False
        return self.runner_up_hits < self.hits

    def __repr__(self):
        return '<AlignmentResult {0:.0%} of {1} | {2}>'.format(
            self.coverage, self.source_count, self.alignment.describe())


def score_alignment(source_records, index, alignment, tolerance, level=sig.STRICT):
    """``(hits, total_distance)`` for one hypothesis."""
    hits = 0
    total = 0.0
    for record in source_records:
        nearest = index.nearest(record.signature(level),
                                alignment.apply(record.point), tolerance)
        if nearest is not None:
            hits += 1
            total += nearest[0]
    return hits, total


def _score_sample(records, options):
    """A small, signature-balanced subset of ``records`` to rank hypotheses on.

    Taking elements round-robin from each signature group - rarest first - keeps
    the discriminating elements in the sample instead of filling it with the one
    type that happens to appear a thousand times.
    """
    limit = max(1, int(options.score_sample_size))
    if len(records) <= limit:
        return records
    groups = sig.group_by_signature(records, sig.STRICT)
    order = sorted(groups, key=lambda s: (len(groups[s]), repr(s)))
    sample = []
    depth = 0
    while len(sample) < limit:
        added = False
        for signature_key in order:
            bucket = groups[signature_key]
            if depth < len(bucket):
                sample.append(bucket[depth])
                added = True
                if len(sample) >= limit:
                    break
        if not added:
            break
        depth += 1
    return sample


def _anchor_records(groups, common_signatures, options):
    """A short, varied list of source records to build hypotheses from."""
    anchors = []
    for signature_key in common_signatures[:options.max_anchor_groups]:
        anchors.extend(groups[signature_key][:options.max_anchors_per_group])
    return anchors


def _translation_hypotheses(source_groups, target_groups, common, options):
    mirrors = (False, True) if options.allow_mirror else (False,)
    for signature_key in common[:options.max_anchor_groups]:
        sources = source_groups[signature_key][:options.max_anchors_per_group]
        targets = target_groups[signature_key][:options.max_anchors_per_group]
        for source in sources:
            for target in targets:
                for mirror in mirrors:
                    yield geom.alignment_from_points(source.point, target.point, mirror)


def _rotation_hypotheses(source_groups, target_groups, common, options):
    mirrors = (False, True) if options.allow_mirror else (False,)
    anchors = _anchor_records(source_groups, common, options)
    tolerance = options.position_tolerance
    for i, first in enumerate(anchors):
        first_targets = target_groups.get(first.signature(sig.STRICT), ())
        if not first_targets:
            continue
        for second in anchors[i + 1:]:
            if geom.xy_length(geom.sub(second.point, first.point)) < options.min_anchor_separation:
                continue
            second_targets = target_groups.get(second.signature(sig.STRICT), ())
            if not second_targets:
                continue
            for target_first in first_targets[:options.max_anchors_per_group]:
                for target_second in second_targets[:options.max_anchors_per_group]:
                    if target_first.key == target_second.key:
                        continue
                    for mirror in mirrors:
                        candidate = geom.alignment_from_pairs(
                            first.point, target_first.point,
                            second.point, target_second.point,
                            mirror=mirror,
                            length_tolerance=tolerance * 2.0,
                            min_separation=options.min_anchor_separation)
                        if candidate is not None:
                            yield candidate


def find_alignment(source_records, target_records, options, seed=None):
    """Search for the best alignment of ``source_records`` onto ``target_records``.

    ``seed`` is an optional alignment to try first - the identity, say, or the
    answer from the previous target view.
    """
    result = AlignmentResult(geom.IDENTITY, 0, 0.0,
                             len(source_records), len(target_records))
    if not source_records or not target_records:
        return result

    source_groups = sig.group_by_signature(source_records, sig.STRICT)
    target_groups = sig.group_by_signature(target_records, sig.STRICT)
    common = sig.rarity_sorted_signatures(source_groups, target_groups)
    if not common:
        return result

    tolerance = options.position_tolerance
    index = PointIndex(target_records, sig.STRICT, tolerance)
    sample = _score_sample(source_records, options)
    sample_size = len(sample)
    perfect = min(len(source_records), len(target_records))

    tested = 0
    seen = set()
    finalists = []
    keep = max(1, int(options.finalist_count))
    winner = None

    candidates = []
    if seed is not None:
        candidates.append(seed)
    candidates.append(geom.IDENTITY)

    def stream():
        for candidate in candidates:
            yield candidate
        for candidate in _translation_hypotheses(source_groups, target_groups,
                                                 common, options):
            yield candidate
        if options.allow_rotation:
            for candidate in _rotation_hypotheses(source_groups, target_groups,
                                                  common, options):
                yield candidate

    for candidate in stream():
        key = candidate.key()
        if key in seen:
            continue
        seen.add(key)
        tested += 1
        hits, total = score_alignment(sample, index, candidate, tolerance)
        if hits:
            finalists.append((hits, -total, candidate))
            if len(finalists) > keep * 4:
                finalists.sort(key=lambda f: (f[0], f[1]), reverse=True)
                del finalists[keep:]
        if hits >= sample_size:
            # perfect on the sample - check it against the whole view, and if it
            # explains everything there is nothing left to look for
            full_hits, full_total = score_alignment(source_records, index,
                                                    candidate, tolerance)
            if full_hits >= perfect:
                winner = (full_hits, -full_total, candidate)
                break
        if tested >= options.max_hypotheses:
            break

    finalists.sort(key=lambda f: (f[0], f[1]), reverse=True)
    del finalists[keep:]

    scored = []
    if winner is not None:
        scored.append(winner)
    whole_view_was_sampled = sample_size == len(source_records)
    for hits, negative_total, candidate in finalists:
        if winner is not None and candidate.key() == winner[2].key():
            continue
        if whole_view_was_sampled:
            scored.append((hits, negative_total, candidate))   # already the full score
        else:
            hits, total = score_alignment(source_records, index, candidate, tolerance)
            scored.append((hits, -total, candidate))
    if not scored:
        return result

    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    best_hits, best_negative_total, best = scored[0]
    runner_up_hits = scored[1][0] if len(scored) > 1 else 0
    return AlignmentResult(best, best_hits, -best_negative_total,
                           len(source_records), len(target_records),
                           hypotheses_tested=tested, runner_up_hits=runner_up_hits)
