# -*- coding: utf-8 -*-
"""What a run did, in a form both the report and the tests can read.

Pure Python - no Revit - so the summarising is covered by the test suite.
"""

from __future__ import division

CREATED = 'created'
SKIPPED = 'skipped'
FAILED = 'failed'

STATUS_ORDER = (CREATED, SKIPPED, FAILED)


class ItemResult(object):
    """The outcome for one source annotation."""

    __slots__ = ('kind', 'status', 'message', 'source_id', 'new_id', 'label')

    def __init__(self, kind, status, source_id, message='', new_id=None, label=''):
        self.kind = kind
        self.status = status
        self.source_id = source_id
        self.message = message
        self.new_id = new_id
        self.label = label

    @property
    def ok(self):
        return self.status == CREATED

    def __repr__(self):
        return '<{0} {1} {2}>'.format(self.kind, self.status, self.message or '')


class ViewReport(object):
    """Everything that happened for one target view."""

    def __init__(self, view_id, view_name, solve_result=None):
        self.view_id = view_id
        self.view_name = view_name
        self.solve_result = solve_result
        self.items = []
        self.notes = []
        self.aborted = None

    def add(self, item):
        self.items.append(item)
        return item

    def note(self, text):
        self.notes.append(text)

    def count(self, status):
        return sum(1 for item in self.items if item.status == status)

    @property
    def created(self):
        return self.count(CREATED)

    @property
    def skipped(self):
        return self.count(SKIPPED)

    @property
    def failed(self):
        return self.count(FAILED)

    @property
    def new_ids(self):
        return [item.new_id for item in self.items
                if item.status == CREATED and item.new_id is not None]

    def by_kind(self):
        """``[(kind, created, skipped, failed), ...]`` sorted by kind."""
        kinds = {}
        for item in self.items:
            row = kinds.setdefault(item.kind, {CREATED: 0, SKIPPED: 0, FAILED: 0})
            row[item.status] = row.get(item.status, 0) + 1
        return [(kind, kinds[kind][CREATED], kinds[kind][SKIPPED], kinds[kind][FAILED])
                for kind in sorted(kinds)]

    def problems(self):
        """Skipped and failed items, worst first - what the user must look at."""
        ordered = [i for i in self.items if i.status == FAILED]
        ordered += [i for i in self.items if i.status == SKIPPED]
        return ordered

    def reasons(self):
        """``[(reason, count), ...]`` for everything that did not get created."""
        counts = {}
        for item in self.problems():
            key = (item.status, item.message or 'no reason given')
            counts[key] = counts.get(key, 0) + 1
        rows = [(status, message, count) for (status, message), count in counts.items()]
        rows.sort(key=lambda row: (-row[2], row[0], row[1]))
        return rows

    def headline(self):
        if self.aborted:
            return '{0}: not run - {1}'.format(self.view_name, self.aborted)
        bits = ['{0} created'.format(self.created)]
        if self.skipped:
            bits.append('{0} skipped'.format(self.skipped))
        if self.failed:
            bits.append('{0} failed'.format(self.failed))
        return '{0}: {1}'.format(self.view_name, ', '.join(bits))

    def __repr__(self):
        return '<ViewReport {0}>'.format(self.headline())


class RunReport(object):
    """Every target view of one run."""

    def __init__(self, source_view_name=''):
        self.source_view_name = source_view_name
        self.views = []

    def add(self, view_report):
        self.views.append(view_report)
        return view_report

    @property
    def created(self):
        return sum(v.created for v in self.views)

    @property
    def skipped(self):
        return sum(v.skipped for v in self.views)

    @property
    def failed(self):
        return sum(v.failed for v in self.views)

    @property
    def aborted_views(self):
        return [v for v in self.views if v.aborted]

    def headline(self):
        if not self.views:
            return 'Nothing to do.'
        parts = ['{0} annotation(s) created in {1} view(s)'.format(
            self.created, len([v for v in self.views if not v.aborted]))]
        if self.skipped:
            parts.append('{0} skipped'.format(self.skipped))
        if self.failed:
            parts.append('{0} failed'.format(self.failed))
        if self.aborted_views:
            parts.append('{0} view(s) not run'.format(len(self.aborted_views)))
        return ', '.join(parts)
