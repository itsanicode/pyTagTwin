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


#: how a placement's offset is expressed
VIEW_FRAME = 'view'      # right/up on the sheet - for elements with no direction
HOST_FRAME = 'host'      # along/across the element itself - for pipes, ducts, conduit


class Placement(object):
    """Where a tag sits relative to the element it labels.

    For anything with a direction - a pipe, a duct, a length of conduit - the
    offset is held in the **element's own frame**: how far along it, as a
    fraction of its length, and how far out to the side. Holding it as a plain
    right/up offset from the element's midpoint looks equivalent and is not: a
    tag placed near the top of a twenty foot riser learns "ten feet up", and
    putting a four foot branch's tag ten feet above *its* midpoint strands it
    eight feet past the end of the pipe. Lengths vary enormously in a riser, so
    that one mistake scatters tags across the sheet.

    ``across`` is a drawing distance and scales with the view scale. ``along``
    is a fraction of the host, so it follows the host instead.
    """

    __slots__ = ('tag_type', 'offset', 'elbow', 'orientation', 'has_leader',
                 'frame', 'along', 'across')

    def __init__(self, tag_type, offset=(0.0, 0.0), elbow=None, orientation=None,
                 has_leader=True, frame=VIEW_FRAME, along=0.0, across=0.0):
        self.tag_type = tag_type
        self.offset = (float(offset[0]), float(offset[1]))
        #: the elbow, held relative to the *head* rather than to the element, so
        #: the leader keeps its shape wherever the head ends up
        self.elbow = None if elbow is None else (float(elbow[0]), float(elbow[1]))
        self.orientation = orientation
        self.has_leader = has_leader
        self.frame = frame
        self.along = float(along)
        self.across = float(across)

    def offset_in_view(self, axis=None, length=None, scale=1.0):
        """The right/up offset to use for a host with this axis and length."""
        if self.frame == HOST_FRAME and axis is not None and length:
            along = self.along * length
            across = self.across * scale
            return (axis[0] * along - axis[1] * across,
                    axis[1] * along + axis[0] * across)
        return (self.offset[0] * scale, self.offset[1] * scale)

    def elbow_in_view(self, scale=1.0):
        """The elbow's offset from the head, at this view scale."""
        if self.elbow is None:
            return None
        return (self.elbow[0] * scale, self.elbow[1] * scale)

    @property
    def distance(self):
        if self.frame == HOST_FRAME:
            return abs(self.across)
        return (self.offset[0] ** 2 + self.offset[1] ** 2) ** 0.5

    def __repr__(self):
        if self.frame == HOST_FRAME:
            return '<Placement {0} along {1:.2f} across {2:.2f}>'.format(
                self.tag_type, self.along, self.across)
        return '<Placement {0} ({1:.2f}, {2:.2f})>'.format(
            self.tag_type, self.offset[0], self.offset[1])


def host_frame_offset(offset, axis, length):
    """Turn a right/up offset into ``(along fraction, across)`` for a host.

    ``axis`` is the host's direction in the view plane, as a unit 2D vector;
    ``length`` is how long the host is once projected onto that plane.
    """
    if not length:
        return 0.0, 0.0
    along = offset[0] * axis[0] + offset[1] * axis[1]
    across = -offset[0] * axis[1] + offset[1] * axis[0]
    return along / length, across


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
    # host-framed and view-framed placements are not comparable, so pick the
    # representative from whichever frame the category mostly uses
    host_framed = [p for p in placements if p.frame == HOST_FRAME]
    pool = host_framed if len(host_framed) * 2 >= len(placements) else [
        p for p in placements if p.frame == VIEW_FRAME]
    if not pool:
        pool = placements
    if len(pool) == 1:
        return pool[0]
    if pool[0].frame == HOST_FRAME:
        mean_a = sum(p.along for p in pool) / float(len(pool))
        mean_b = sum(p.across for p in pool) / float(len(pool))
        return min(pool, key=lambda p: (p.along - mean_a) ** 2 + (p.across - mean_b) ** 2)
    mean_a = sum(p.offset[0] for p in pool) / float(len(pool))
    mean_b = sum(p.offset[1] for p in pool) / float(len(pool))
    return min(pool, key=lambda p: (p.offset[0] - mean_a) ** 2
               + (p.offset[1] - mean_b) ** 2)


class LayoutRecipe(object):
    """The arrangement learned from the reference view."""

    def __init__(self):
        self.by_signature = {}
        self.by_category = {}
        self.tag_types = {}
        self.population = {}
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

    def density(self, signature):
        """Share of that kind of element the reference view actually tagged.

        Tagging every pipe when the reference tagged three of them is how a
        clean drawing turns into a thicket, so the density is copied too.
        """
        tagged = len(self.by_signature.get(signature, ()))
        if not tagged:
            return 0.0
        total = self.population.get(signature, tagged)
        if total <= 0:
            return 1.0
        return min(1.0, tagged / float(total))

    def tags_wanted(self, signature, available):
        """How many of ``available`` elements of this kind should carry a tag."""
        if signature not in self.by_signature:
            return 0
        if not available:
            return 0
        wanted = int(round(self.density(signature) * available))
        return max(1, min(available, wanted))

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

    def tagged_kinds(self):
        """``[(signature, tags, elements, density), ...]``, busiest first."""
        rows = []
        for signature in self.by_signature:
            tagged = len(self.by_signature[signature])
            rows.append((signature, tagged, self.population.get(signature, tagged),
                         self.density(signature)))
        rows.sort(key=lambda row: (-row[1], repr(row[0])))
        return rows

    def __repr__(self):
        return '<LayoutRecipe {0}>'.format(self.describe())


def learn(samples, population=None):
    """Build a recipe from the tags of a reference view.

    ``population`` is how many elements of each kind the reference view holds,
    tagged or not, which is what makes the tagging *density* reproducible.
    """
    recipe = LayoutRecipe()
    recipe.population = dict(population or {})
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


def assign(hosts, recipe):
    """Work out a placement for every host in the view being arranged.

    Hosts are ranked within their own signature using the same reading order
    the recipe was built with, so a staggered run replays in the same sequence.

    The placements come back unscaled: turning one into a position needs the
    target host's own axis and length, which only the caller has.
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
        assignments.append(Assignment(host.key, placement, how, rank))
    return assignments


def summarise(assignments):
    """``{how: count}`` - what the report shows."""
    counts = {}
    for assignment in assignments:
        counts[assignment.how] = counts.get(assignment.how, 0) + 1
    return counts
