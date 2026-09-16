# -*- coding: utf-8 -*-
"""Tests for the pure-Python matching engine. Run with ``python run_tests.py``."""

from __future__ import division

import math

import model_fixtures as fx
from tagtwin import geom, signature as sig
from tagtwin.matching import match_elements, solve
from tagtwin.options import MatchOptions

CASES = []


def case(func):
    CASES.append(func)
    return func


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

@case
def test_alignment_roundtrip():
    for alignment in (geom.Alignment(0.0, False, (5, 0, 0)),
                      geom.Alignment(math.pi / 3, False, (1, 2, 3)),
                      geom.Alignment(-2.1, True, (-4, 7, 0.5))):
        point = (1.7, -2.3, 0.9)
        back = alignment.inverse().apply(alignment.apply(point))
        assert all(approx(back[i], point[i], 1e-9) for i in range(3)), alignment


@case
def test_alignment_preserves_distance():
    alignment = geom.Alignment(0.9, True, (3, -2, 1))
    a, b = (0.0, 0.0, 0.0), (3.0, 4.0, 12.0)
    assert approx(geom.distance(a, b),
                  geom.distance(alignment.apply(a), alignment.apply(b)), 1e-9)


@case
def test_mirror_flips_handedness():
    alignment = geom.Alignment(0.0, True, (0, 0, 0))
    assert alignment.apply((1.0, 2.0, 3.0)) == (1.0, -2.0, 3.0)
    # a mirror must reverse the sign of the cross product
    x = alignment.apply_vector((1.0, 0.0, 0.0))
    y = alignment.apply_vector((0.0, 1.0, 0.0))
    assert geom.cross(x, y)[2] < 0


@case
def test_alignment_from_pairs_rejects_mismatched_spans():
    assert geom.alignment_from_pairs((0, 0, 0), (0, 0, 0),
                                     (10, 0, 0), (25, 0, 0)) is None
    # and accepts a consistent pair
    found = geom.alignment_from_pairs((0, 0, 0), (5, 5, 0), (10, 0, 0), (5, 15, 0))
    assert found is not None
    assert approx(math.degrees(found.angle), 90.0, 1e-6)


@case
def test_fit_alignment_recovers_transform():
    truth = geom.Alignment(math.radians(37.0), False, (12.0, -3.0, 2.0))
    points = [(0, 0, 0), (5, 1, 0), (2, 7, 3), (-4, 2, 1)]
    pairs = [(p, truth.apply(p)) for p in points]
    fitted = geom.fit_alignment(pairs, mirror=False)
    assert approx(fitted.angle, truth.angle, 1e-9)
    assert all(approx(fitted.offset[i], truth.offset[i], 1e-9) for i in range(3))


@case
def test_snap_angle():
    nearly = geom.Alignment(math.radians(90.02), False, (0, 0, 0))
    assert approx(math.degrees(geom.snap_angle(nearly, 90.0, 0.5).angle), 90.0, 1e-9)
    # outside the tolerance the fitted angle is left alone
    slanted = geom.Alignment(math.radians(83.0), False, (0, 0, 0))
    assert approx(math.degrees(geom.snap_angle(slanted, 90.0, 0.5).angle), 83.0, 1e-9)


# --------------------------------------------------------------------------
# signatures
# --------------------------------------------------------------------------

@case
def test_signature_is_transform_invariant():
    alignment = geom.Alignment(math.radians(90.0), True, (40.0, 12.0, 0.0))
    source = fx.build_suite()
    target = fx.transformed_suite(alignment)
    assert (sorted(r.signature(sig.STRICT) for r in source)
            == sorted(r.signature(sig.STRICT) for r in target))


@case
def test_orientation_classes():
    assert sig.classify_direction((0, 0, 1)) == sig.VERTICAL
    assert sig.classify_direction((1, 0, 0)) == sig.HORIZONTAL
    assert sig.classify_direction((1, 0, 1)) == sig.SLOPED
    assert sig.classify_direction(None) == sig.POINT


@case
def test_identical_elements_found():
    """What "identical" means depends on the level you ask at."""
    suite = fx.build_suite()
    valves = [r for r in suite if r.category == fx.ACCESSORY]
    assert len(valves) == 3
    # the hot water valve is the same family and type as the two cold water
    # ones, so it is only identical to them once the system is ignored
    assert len(sig.identical_in(suite, valves[0], sig.STRICT)) == 2
    assert len(sig.identical_in(suite, valves[0], sig.LOOSE)) == 3


# --------------------------------------------------------------------------
# solving: the cases a drafter actually has
# --------------------------------------------------------------------------

def _solve_against(alignment, **kwargs):
    options = kwargs.pop('options', MatchOptions())
    source = fx.build_suite()
    target = fx.transformed_suite(alignment, **kwargs)
    return source, target, solve(source, target, options)


def _check_pairs_are_correct(result, source):
    """Element N of the source must map onto element N of the target."""
    by_key = dict((r.key, r) for r in source)
    for match in result.match_result.matches:
        position = list(by_key).index(match.source.key) + 1
        expected = 2000 + position
        assert match.target.key == expected, \
            'source {0} matched {1}, expected {2}'.format(
                match.source.key, match.target.key, expected)


@case
def test_pure_translation():
    truth = geom.Alignment(0.0, False, (40.0, 0.0, 0.0))
    source, _, result = _solve_against(truth)
    assert result.coverage == 1.0, result
    assert result.alignment.key() == truth.key(), result.alignment
    _check_pairs_are_correct(result, source)
    assert result.verdict() == 'excellent'


@case
def test_rotation_and_translation():
    truth = geom.Alignment(math.radians(90.0), False, (30.0, -18.0, 0.0))
    source, _, result = _solve_against(truth)
    assert result.coverage == 1.0, result
    assert approx(result.alignment.angle, truth.angle, 1e-6)
    _check_pairs_are_correct(result, source)


@case
def test_mirrored_suite():
    """Handed suites - the back-to-back bathroom case - must still match."""
    truth = geom.Alignment(math.radians(180.0), True, (24.0, 6.0, 0.0))
    source, _, result = _solve_against(truth)
    assert result.coverage == 1.0, result
    assert result.alignment.mirror is True
    _check_pairs_are_correct(result, source)


@case
def test_mirror_can_be_disabled():
    """With mirroring off a handed suite only matches where it is symmetric."""
    truth = geom.Alignment(0.0, True, (24.0, 0.0, 0.0))
    source = fx.build_suite()
    target = fx.transformed_suite(truth)
    with_mirror = solve(source, target, MatchOptions(allow_mirror=True))
    assert with_mirror.coverage == 1.0, with_mirror
    without = solve(source, target, MatchOptions(allow_mirror=False))
    assert without.coverage < with_mirror.coverage
    # everything off the mirror plane is left behind, and is reported as such
    unmatched = set(r.key for r in without.match_result.unmatched_source)
    off_plane = set(r.key for r in source if abs(r.point[1]) > 1e-9)
    assert unmatched == off_plane, (unmatched, off_plane)


@case
def test_vertical_offset_between_floors():
    truth = geom.Alignment(0.0, False, (0.0, 0.0, 12.0))
    source, _, result = _solve_against(truth)
    assert result.coverage == 1.0, result
    assert approx(result.alignment.offset[2], 12.0, 1e-6)


@case
def test_identity_when_views_show_the_same_elements():
    source = fx.build_suite()
    result = solve(source, source, MatchOptions())
    assert result.coverage == 1.0
    assert result.alignment.is_identity(), result.alignment
    assert all(m.source.key == m.target.key for m in result.match_result.matches)


@case
def test_modelling_jitter_is_absorbed():
    truth = geom.Alignment(math.radians(90.0), False, (30.0, 5.0, 0.0))
    options = MatchOptions(position_tolerance=0.08)
    source, _, result = _solve_against(truth, options=options, jitter=0.01)
    assert result.coverage == 1.0, result
    _check_pairs_are_correct(result, source)


@case
def test_missing_and_extra_elements():
    truth = geom.Alignment(0.0, False, (40.0, 0.0, 0.0))
    source, target, result = _solve_against(truth, drop_keys=(3, 11), extra=4)
    matched = len(result.match_result.matches)
    assert matched == len(source) - 2, result
    assert len(result.match_result.unmatched_source) == 2
    # the four unrelated elements must stay unmatched
    assert len(result.match_result.unmatched_target) == 4
    assert result.coverage == 0.9
    assert result.verdict() in ('good', 'excellent'), result.confidence()


@case
def test_relaxed_levels_rescue_resized_elements():
    """A branch cut shorter in the second suite still finds its twin."""
    truth = geom.Alignment(0.0, False, (40.0, 0.0, 0.0))
    source = fx.build_suite()
    target = fx.transformed_suite(truth)
    resized = target[2]
    resized.length = round(resized.length - 0.5, 2)   # different STRICT signature

    strict_only = solve(source, target, MatchOptions(use_relaxed_levels=False))
    assert len(strict_only.match_result.unmatched_source) == 1

    relaxed = solve(source, target, MatchOptions(use_relaxed_levels=True,
                                                 relaxed_tolerance_factor=2.0))
    assert relaxed.coverage == 1.0, relaxed
    rescued = [m for m in relaxed.match_result.matches if not m.is_exact]
    assert len(rescued) == 1 and rescued[0].level == sig.MEDIUM


@case
def test_unrelated_views_do_not_match():
    source = fx.build_suite()
    target = [fx._point_element(3000 + n, 'Walls', 77, (n * 4.0, 0.0, 0.0))
              for n in range(10)]
    result = solve(source, target, MatchOptions())
    assert not result.match_result.matches
    assert result.confidence() == 0.0
    assert result.verdict() == 'poor'


@case
def test_ambiguity_is_reported():
    """Two identical valves a hair apart cannot be told apart - say so."""
    source = fx.build_suite()
    target = fx.transformed_suite(geom.Alignment(0.0, False, (40.0, 0.0, 0.0)))
    valves = [r for r in target if r.category == fx.ACCESSORY]
    valves[1].point = (valves[0].point[0] + 0.005,
                       valves[0].point[1], valves[0].point[2])
    result = solve(source, target, MatchOptions())
    assert result.match_result.ambiguous_count >= 1, result.match_result.matches
    assert result.confidence() < 1.0


@case
def test_id_map_is_one_to_one():
    truth = geom.Alignment(math.radians(90.0), True, (17.0, 4.0, 0.0))
    _, _, result = _solve_against(truth)
    id_map = result.id_map
    assert len(set(id_map.values())) == len(id_map)


@case
def test_refinement_improves_a_rough_start():
    """Matching under a deliberately wrong transform is rescued by refinement."""
    truth = geom.Alignment(0.0, False, (40.0, 0.0, 0.0))
    source = fx.build_suite()
    target = fx.transformed_suite(truth)
    rough = geom.Alignment(0.0, False, (40.05, 0.02, 0.0))
    options = MatchOptions(position_tolerance=0.1)
    before = match_elements(source, target, rough, options)
    after = solve(source, target, options)
    assert after.match_result.total_distance < before.total_distance
    assert after.coverage == 1.0


@case
def test_empty_inputs_are_safe():
    options = MatchOptions()
    assert solve([], [], options).coverage == 0.0
    assert solve(fx.build_suite(), [], options).coverage == 0.0
    assert solve([], fx.build_suite(), options).coverage == 0.0


@case
def test_options_round_trip_through_config():
    options = MatchOptions(position_tolerance=0.05, allow_mirror=False)
    restored = MatchOptions.from_dict(options.to_dict())
    assert restored.to_dict() == options.to_dict()
    # unknown keys from an older/newer config must not blow up
    data = options.to_dict()
    data['some_removed_option'] = 4
    assert MatchOptions.from_dict(data).position_tolerance == 0.05


@case
def test_hypothesis_budget_is_respected():
    options = MatchOptions(max_hypotheses=5)
    truth = geom.Alignment(math.radians(45.0), False, (13.0, 9.0, 0.0))
    source = fx.build_suite()
    target = fx.transformed_suite(truth)
    result = solve(source, target, options)
    assert result.alignment_result.hypotheses_tested <= 6


@case
def test_score_sample_is_capped_and_balanced():
    """Hypothesis ranking must stay cheap on a big view without going blind."""
    from tagtwin.align import _score_sample
    records = []
    key = 0
    for copy in range(60):
        for record in fx.build_suite(start_key=0):
            key += 1
            records.append(sig.ElementRecord(
                key, record.category, record.type_id,
                (record.point[0] + copy * 40.0, record.point[1], record.point[2]),
                record.system_id, record.size, record.length,
                record.orientation, record.axis, record.label))
    options = MatchOptions(score_sample_size=120)
    sample = _score_sample(records, options)
    assert len(sample) == 120
    # every distinct kind of element is represented, not just the common ones
    all_signatures = set(r.signature(sig.STRICT) for r in records)
    assert set(r.signature(sig.STRICT) for r in sample) == all_signatures
    # and a view smaller than the cap is used whole
    small = fx.build_suite()
    assert _score_sample(small, options) is small


@case
def test_large_model_still_matches():
    """Sampling ranks the hypotheses; the finalists are checked on everything."""
    truth = geom.Alignment(math.radians(90.0), False, (500.0, 120.0, 0.0))
    source = []
    target = []
    key = 0
    for copy in range(40):
        spread = geom.Alignment(0.0, False, (copy % 10 * 40.0, copy // 10 * 40.0, 0.0))
        for record in fx.build_suite(start_key=0):
            key += 1
            point = spread.apply(record.point)
            source.append(sig.ElementRecord(
                key, record.category, record.type_id, point, record.system_id,
                record.size, record.length, record.orientation, record.axis))
            target.append(sig.ElementRecord(
                500000 + key, record.category, record.type_id, truth.apply(point),
                record.system_id, record.size, record.length, record.orientation,
                record.axis))
    result = solve(source, target, MatchOptions())
    assert len(source) == 800
    assert result.coverage == 1.0, result
    assert approx(result.alignment.angle, truth.angle, 1e-6)


@case
def test_basis_vectors_match_the_transform():
    """The Revit ``Transform`` is built from these - they must agree exactly."""
    for alignment in (geom.Alignment(math.radians(30.0), False, (1, 2, 3)),
                      geom.Alignment(math.radians(-115.0), True, (0, 0, 0))):
        for axis, basis in (((1, 0, 0), alignment.basis_x),
                            ((0, 1, 0), alignment.basis_y),
                            ((0, 0, 1), alignment.basis_z)):
            applied = alignment.apply_vector(axis)
            assert all(approx(applied[i], basis[i], 1e-12) for i in range(3)), \
                (alignment, axis, applied, basis)


@case
def test_report_counts_and_reasons():
    from tagtwin import results
    report = results.ViewReport(7, 'Level 2 - Plumbing')
    report.add(results.ItemResult('Tag', results.CREATED, 1))
    report.add(results.ItemResult('Tag', results.CREATED, 2))
    report.add(results.ItemResult('Tag', results.SKIPPED, 3, 'no twin'))
    report.add(results.ItemResult('Dimension', results.FAILED, 4, 'bad reference'))
    assert (report.created, report.skipped, report.failed) == (2, 1, 1)
    assert report.by_kind() == [('Dimension', 0, 0, 1), ('Tag', 2, 1, 0)]
    # failures are listed before skips - they are what needs attention
    assert [i.status for i in report.problems()] == [results.FAILED, results.SKIPPED]
    assert report.reasons() == [(results.FAILED, 'bad reference', 1),
                                (results.SKIPPED, 'no twin', 1)]
    assert 'Level 2 - Plumbing: 2 created, 1 skipped, 1 failed' == report.headline()


@case
def test_run_report_aggregates_views():
    from tagtwin import results
    run = results.RunReport('Suite 158 riser')
    first = run.add(results.ViewReport(1, 'Suite 160 riser'))
    first.add(results.ItemResult('Tag', results.CREATED, 1))
    second = run.add(results.ViewReport(2, 'Suite 162 riser'))
    second.aborted = 'the 3D view is not locked'
    assert run.created == 1
    assert len(run.aborted_views) == 1
    assert '1 annotation(s) created in 1 view(s)' in run.headline()
    assert '1 view(s) not run' in run.headline()
