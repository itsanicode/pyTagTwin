# -*- coding: utf-8 -*-
"""Learn a tag arrangement from a finished view and replay it on another.

Re-hosting tags onto matched elements needs a correct element-to-element map
across the whole view, and when that map is thin nothing gets placed at all.
Revit already solves hosting perfectly well with Tag All. What it does not solve
- and what is actually the work - is *where each tag sits*.

So this module learns placement, not identity. A placement is recorded as an
offset from the tagged element **in view coordinates** (right and up on the
sheet), keyed on what kind of element it is rather than on which one. Nothing
here needs the two views to line up in space, which is why it keeps working
where matching does not.

Identical elements are usually staggered so their tags do not collide - three
valves in a riser get three different offsets. That is preserved by ordering:
the tags of one signature are stored in the order their elements appear in the
view, and replayed in that same order onto the target view's elements.

Pure Python, no Revit.
"""

from __future__ import division


class Placement(object):
    """Where a tag sits relative to the element it labels, in view axes."""

    __slots__ = ('tag_type', 'offset', 'elbow', 'orientation', 'has_leader')

    def __init__(self, tag_type, offset, elbow=None, orientation=None,
                 has_leader=True):
        self.tag_type = tag_type
        self.offset = (float(offset[0]), float(offset[1]))
        self.elbow = None if elbow is None else (float(elbow[0]), float(elbow[1]))
        self.orientation = orientation
        self.has_leader = has_leader

    def scaled(self, factor):
        """The same placement at another view scale."""
        if factor == 1.0:
            return self
        elbow = None if self.elbow is None else (self.elbow[0] * factor,
                                                 self.elbow[1] * factor)
        return Placement(self.tag_type,
                         (self.offset[0] * factor, self.offset[1] * factor),
                         elbow, self.orientation, self.has_leader)

    @property
    def distance(self):
        return (self.offset[0] ** 2 + self.offset[1] ** 2) ** 0.5

    def __repr__(self):
        return '<Placement {0} ({1:.2f}, {2:.2f})>'.format(
            self.tag_type, self.offset[0], self.offset[1])


class TagSample(object):
    """One tag read out of the reference view."""

    __slots__ = ('signature', 'category', 'order_key', 'placement')

    def __init__(self, signature, category, order_key, placement):
        self.signature = signature
        self.category = category
        self.order_key = order_key
        self.placement = placement


class TargetHost(object):
    """One element in the view being arranged."""

    __slots__ = ('key', 'signature', 'category', 'order_key')

    def __init__(self, key, signature, category, order_key):
        self.key = key
        self.signature = signature
        self.category = category
        self.order_key = order_key


#: how a placement was arrived at, worst last
EXACT = 'same kind of element'
CATEGORY = 'average for the category'
NONE = 'no guidance'


def sort_key(order_key):
    """Top to bottom, then left to right, as a drafter reads a view.

    Any deterministic geometric rule works as long as both views use it; this
    one matches the order tags are usually staggered in.
    """
    return (-order_key[1], order_key[0])


def _average(placements):
    """A representative placement for a group - the median-ish one.

    The element nearest the average offset is used rather than a synthetic
    mean, so the result is a placement that a drafter actually chose.
    """
    if not placements:
        return None
    if len(placements) == 1:
        return placements[0]
    mean_right = sum(p.offset[0] for p in placements) / float(len(placements))
    mean_up = sum(p.offset[1] for p in placements) / float(len(placements))

    def distance_to_mean(placement):
        return ((placement.offset[0] - mean_right) ** 2
                + (placement.offset[1] - mean_up) ** 2)
    return min(placements, key=distance_to_mean)


class LayoutRecipe(object):
    """The arrangement learned from the reference view."""

    def __init__(self):
        self.by_signature = {}
        self.by_category = {}
        self.tag_types = {}
        self.sample_count = 0

    # -- reading ----------------------------------------------------------

    @property
    def signatures(self):
        return set(self.by_signature)

    @property
    def categories(self):
        return set(self.by_category)

    def tag_type_for(self, category):
        """The tag type this category is tagged with in the reference view.

        The commonest one, so a stray tag of another type does not decide it.
        """
        counts = self.tag_types.get(category)
        if not counts:
            return None
        return max(sorted(counts), key=lambda type_id: counts[type_id])

    def placement_for(self, signature, category, rank=0):
        """``(placement, how)`` for the ``rank``-th element of its kind."""
        ordered = self.by_signature.get(signature)
        if ordered:
            # cycle rather than clamp: a staggered run of three offsets keeps
            # alternating instead of piling every extra tag on the last one
            return ordered[rank % len(ordered)], EXACT
        fallback = self.by_category.get(category)
        if fallback is not None:
            return fallback, CATEGORY
        return None, NONE

    def describe(self):
        return ('{0} tag(s) over {1} kind(s) of element in {2} '
                'category/categories'.format(self.sample_count,
                                             len(self.by_signature),
                                             len(self.by_category)))

    def __repr__(self):
        return '<LayoutRecipe {0}>'.format(self.describe())


def learn(samples):
    """Build a recipe from the tags of a reference view."""
    recipe = LayoutRecipe()
    grouped = {}
    per_category = {}
    for sample in samples:
        grouped.setdefault(sample.signature, []).append(sample)
        per_category.setdefault(sample.category, []).append(sample.placement)
        counts = recipe.tag_types.setdefault(sample.category, {})
        type_id = sample.placement.tag_type
        counts[type_id] = counts.get(type_id, 0) + 1
        recipe.sample_count += 1

    for signature, entries in grouped.items():
        entries.sort(key=lambda s: sort_key(s.order_key))
        recipe.by_signature[signature] = [e.placement for e in entries]
    for category, placements in per_category.items():
        recipe.by_category[category] = _average(placements)
    return recipe


class Assignment(object):
    """Where one target tag should go, and how confidently."""

    __slots__ = ('key', 'placement', 'how', 'rank')

    def __init__(self, key, placement, how, rank):
        self.key = key
        self.placement = placement
        self.how = how
        self.rank = rank

    @property
    def is_guided(self):
        return self.placement is not None

    def __repr__(self):
        return '<Assignment {0} {1} ({2})>'.format(self.key, self.placement,
                                                   self.how)


def assign(hosts, recipe, scale=1.0):
    """Work out a placement for every host in the view being arranged.

    Hosts are ranked within their own signature using the same reading order
    the recipe was built with, so a staggered run replays in the same sequence.
    """
    ranked = {}
    grouped = {}
    for host in hosts:
        grouped.setdefault(host.signature, []).append(host)
    for signature, entries in grouped.items():
        entries.sort(key=lambda h: sort_key(h.order_key))
        for rank, host in enumerate(entries):
            ranked[host.key] = rank

    assignments = []
    for host in hosts:
        rank = ranked[host.key]
        placement, how = recipe.placement_for(host.signature, host.category, rank)
        if placement is not None and scale != 1.0:
            placement = placement.scaled(scale)
        assignments.append(Assignment(host.key, placement, how, rank))
    return assignments


def summarise(assignments):
    """``{how: count}`` - what the report shows."""
    counts = {}
    for assignment in assignments:
        counts[assignment.how] = counts.get(assignment.how, 0) + 1
    return counts
