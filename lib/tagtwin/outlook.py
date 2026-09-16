# -*- coding: utf-8 -*-
"""Will this run actually place anything?

Coverage over *all* model elements answers "are these two views the same
thing", which is a fair question but the wrong one to refuse a run on. A
sanitary riser is mostly untagged pipe and fittings: half of it can fail to
match while every element that carries a tag matches perfectly.

So the decision to run is made on the annotations themselves - how many of them
have a matched host to hang on - and the element coverage stays as background
information.

Pure Python, no Revit: the items only have to expose ``kind``, ``host_ids`` and
``references_model``.
"""

from __future__ import division


class AnnotationOutlook(object):
    """What would happen to each source annotation in one target view."""

    def __init__(self, placeable, blocked, free, hosted_total, hosted_matched):
        self.placeable = placeable
        self.blocked = blocked
        self.free = free
        self.hosted_total = hosted_total
        self.hosted_matched = hosted_matched

    @property
    def total(self):
        return self.placeable + self.blocked

    @property
    def share(self):
        """Share of the source annotations that can be placed, 0.0 - 1.0."""
        if not self.total:
            return 0.0
        return self.placeable / float(self.total)

    @property
    def host_coverage(self):
        """Share of the *annotated* elements that found a twin.

        The number that actually predicts whether a run is worth doing.
        """
        if not self.hosted_total:
            return 0.0
        return self.hosted_matched / float(self.hosted_total)

    @property
    def is_worth_running(self):
        return self.placeable > 0

    def summary(self):
        if not self.total:
            return 'nothing to copy'
        if not self.placeable:
            return 'none of the {0} annotations can be placed'.format(self.total)
        text = '{0} of {1} annotations can be placed'.format(self.placeable, self.total)
        if self.hosted_total:
            text += ' ({0:.0%} of tagged elements matched)'.format(self.host_coverage)
        return text

    def __repr__(self):
        return '<AnnotationOutlook {0}>'.format(self.summary())


def assess(items, id_map, needs_all_hosts=()):
    """Work out how many of ``items`` could be re-created under ``id_map``.

    ``needs_all_hosts`` names the kinds that are all-or-nothing: a dimension
    measures between specific elements, so losing one reference loses the
    dimension, while a tag only needs one of its elements to have a twin.
    """
    needs_all = set(needs_all_hosts)
    placeable = blocked = free = 0
    hosted = set()
    matched = set()
    for item in items:
        if not item.references_model:
            free += 1
            placeable += 1
            continue
        hosts = list(item.host_ids or ())
        if not hosts:
            blocked += 1
            continue
        hosted.update(hosts)
        found = [host for host in hosts if host in id_map]
        matched.update(found)
        if item.kind in needs_all:
            ok = len(found) == len(hosts)
        else:
            ok = bool(found)
        if ok:
            placeable += 1
        else:
            blocked += 1
    return AnnotationOutlook(placeable, blocked, free, len(hosted), len(matched))
