# -*- coding: utf-8 -*-
"""Tie the pieces together: collect, match, replicate.

The source view is read **once** and reused for every target view, because
reading and fingerprinting a view is the expensive half of a run.
"""

from __future__ import division

from tagtwin import matching, outlook, results, signature as sig
from tagtwin.revit import annotations, collect, compat

#: annotations that need every one of their references, not just one
NEEDS_ALL_HOSTS = (annotations.KIND_DIMENSION, annotations.KIND_SPOT)


class SourceContext(object):
    """The source view, collected once."""

    def __init__(self, doc, view, records, items, unsupported):
        self.doc = doc
        self.view = view
        self.records = records
        self.items = items
        self.unsupported = unsupported

    @property
    def name(self):
        return self.view.Name

    @property
    def annotation_count(self):
        return len(self.items)

    def kind_counts(self):
        counts = {}
        for item in self.items:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return [(kind, counts[kind]) for kind in sorted(counts)]


class TargetAnalysis(object):
    """What was worked out about one target view, before anything is changed."""

    def __init__(self, view, records, solve_result, annotation_outlook=None):
        self.view = view
        self.records = records
        self.solve_result = solve_result
        self.outlook = annotation_outlook

    @property
    def name(self):
        return self.view.Name

    @property
    def view_id(self):
        return compat.eid_value(self.view.Id)

    @property
    def coverage(self):
        return self.solve_result.coverage

    @property
    def confidence(self):
        return self.solve_result.confidence()

    @property
    def verdict(self):
        return self.solve_result.verdict()

    @property
    def matched(self):
        return len(self.solve_result.match_result.matches)

    @property
    def placeable(self):
        return self.outlook.placeable if self.outlook else 0

    @property
    def is_worth_running(self):
        """Whether anything at all would be created in this view.

        Deliberately not "does the view match well". A riser is mostly untagged
        pipework, so element coverage can look poor while every tagged element
        matched perfectly.
        """
        return bool(self.outlook and self.outlook.is_worth_running)

    def describe_alignment(self):
        return self.solve_result.alignment.describe()


def build_source(doc, view, options):
    """Read the source view: its model elements and its annotations."""
    records = collect.collect_model_elements(doc, view, options)
    items, unsupported = annotations.collect_annotations(doc, view, options)
    return SourceContext(doc, view, records, items, unsupported)


def analyze(source, target_view, options):
    """Work out how ``target_view`` lines up with the source. Changes nothing."""
    records = collect.collect_model_elements(source.doc, target_view, options)
    solve_result = matching.solve(source.records, records, options)
    annotation_outlook = outlook.assess(source.items, solve_result.id_map,
                                        NEEDS_ALL_HOSTS)
    return TargetAnalysis(target_view, records, solve_result, annotation_outlook)


def replicate(source, analysis, options):
    """Rebuild the source annotations in the analysed view.

    Must be called inside an open transaction. Never raises for a single
    annotation Revit refuses - that lands in the report instead.
    """
    report = results.ViewReport(analysis.view_id, analysis.name,
                                analysis.solve_result)
    replicator = annotations.Replicator(source.doc, source.view, analysis.view,
                                        analysis.solve_result, options)
    blockers = replicator.blockers(source.items)
    if blockers:
        report.aborted = '; '.join(blockers)
        return report
    if not analysis.solve_result.match_result.matches:
        needs_model = any(item.references_model for item in source.items)
        if needs_model:
            report.aborted = ('no element in this view matches the source view - '
                              'there is nothing to hang the tags on')
            return report

    report.note('Alignment: {0}'.format(analysis.describe_alignment()))
    report.note('Matched {0} of {1} source elements ({2:.0%}, {3})'.format(
        analysis.matched, analysis.solve_result.match_result.source_count,
        analysis.coverage, analysis.verdict))
    if analysis.outlook is not None:
        report.note('Annotations: {0}'.format(analysis.outlook.summary()))
    if replicator.scale != 1.0:
        report.note('View scale differs - annotation offsets scaled by '
                    '{0:.2f}'.format(replicator.scale))
    if replicator.offset_mode == 'view':
        report.note('The views look different ways - offsets kept in view '
                    'coordinates')

    replicator.run(source.items, report)
    for item in source.unsupported:
        report.add(item)
    return report


def find_identical_elements(doc, view, element_ids, options, level=sig.STRICT):
    """Every element in ``view`` matching the signature of the given elements."""
    records = collect.collect_model_elements(doc, view, options)
    by_key = dict((record.key, record) for record in records)
    wanted = set()
    missing = []
    for element_id in element_ids:
        record = by_key.get(element_id)
        if record is None:
            missing.append(element_id)
        else:
            wanted.add(record.signature(level))
    matches = [r for r in records if r.signature(level) in wanted]
    return matches, missing


def candidate_target_views(doc, source_view):
    """Views a run could sensibly write into, best candidates first."""
    from Autodesk.Revit import DB
    source_id = compat.eid_value(source_view.Id)
    try:
        source_type = source_view.ViewType
    except Exception:
        source_type = None
    same_type = []
    others = []
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            if view.IsTemplate or compat.eid_value(view.Id) == source_id:
                continue
            if isinstance(view, (DB.ViewSheet, DB.ViewSchedule)):
                continue
            if view.ViewType in (DB.ViewType.Legend, DB.ViewType.DrawingSheet,
                                 DB.ViewType.Schedule, DB.ViewType.ProjectBrowser,
                                 DB.ViewType.SystemBrowser, DB.ViewType.Internal):
                continue
        except Exception:
            continue
        if source_type is not None and view.ViewType == source_type:
            same_type.append(view)
        else:
            others.append(view)
    same_type.sort(key=lambda v: v.Name)
    others.sort(key=lambda v: (str(v.ViewType), v.Name))
    return same_type, others
