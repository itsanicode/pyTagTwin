# -*- coding: utf-8 -*-
"""Tag a view the way another view is tagged.

Three steps, and the fragile one is gone:

1. **Learn** the arrangement of the reference view - for every tag, how far it
   sits from its element, measured along the view's own right/up axes.
2. **Tag** whatever is untagged in the target view, using the tag type the
   reference view uses for that category. This is Revit's Tag All, except that
   the tag type is taken from the drawing you are copying rather than picked in
   a dialog.
3. **Arrange** every one of those tags onto the learned offsets.

No element-to-element correspondence between the views is needed anywhere, so
there is nothing to fail to match. The two views do not even have to be the same
shape - only to contain the same *kinds* of element.
"""

from __future__ import division

import math

from Autodesk.Revit import DB

from tagtwin import declutter, geom, layout, margin, results
from tagtwin.revit import collect, compat

#: what a tag's placement is recorded against
TAG_KIND = 'Tag'


def _view_offset(view, origin, point):
    """``point - origin`` expressed along the view's right/up axes."""
    delta = geom.sub(point, origin)
    right, up, _ = compat.view_axes(view)
    return (geom.dot(delta, right), geom.dot(delta, up))


def _model_point(view, origin, offset):
    """The inverse: a right/up offset put back into model space."""
    right, up, _ = compat.view_axes(view)
    moved = geom.add(origin, geom.add(geom.scale(right, offset[0]),
                                      geom.scale(up, offset[1])))
    return compat.to_xyz(moved)


def _host_frame(view, record):
    """``(unit axis in the view plane, projected length)`` for a linear host.

    A pipe pointing straight at the viewer projects to nothing, and there is no
    sensible "along" for it, so it falls back to a plain view offset.
    """
    axis = getattr(record, 'axis', None)
    if not axis:
        return None, 0.0
    right, up, _ = compat.view_axes(view)
    flat = (geom.dot(axis, right), geom.dot(axis, up))
    length = math.sqrt(flat[0] * flat[0] + flat[1] * flat[1])
    if length < 1e-6:
        return None, 0.0
    return (flat[0] / length, flat[1] / length), length


def _order_key(view, point):
    """Where a point sits on the sheet, for reading order."""
    right, up, _ = compat.view_axes(view)
    return (geom.dot(point, right), geom.dot(point, up))


class ViewTags(object):
    """The tags of one view, indexed by the element they label."""

    def __init__(self, doc, view):
        self.doc = doc
        self.view = view
        self.tags = []
        self.by_host = {}
        collector = DB.FilteredElementCollector(doc, view.Id)
        for tag in collector.OfClass(DB.IndependentTag):
            try:
                hosts = compat.tagged_element_ids(tag)
            except Exception:
                continue
            self.tags.append(tag)
            for host_id in hosts:
                self.by_host.setdefault(host_id, []).append(tag)

    def has_tag_of_type(self, host_id, type_id):
        for tag in self.by_host.get(host_id, ()):
            try:
                if compat.eid_value(tag.GetTypeId()) == type_id:
                    return True
            except Exception:
                continue
        return False

    def register(self, host_id, tag):
        self.tags.append(tag)
        self.by_host.setdefault(host_id, []).append(tag)


def _records_by_key(doc, view, options):
    records = collect.collect_model_elements(doc, view, options)
    return dict((record.key, record) for record in records)


def learn_view(doc, view, options, level):
    """Read the tag arrangement out of a finished view."""
    records = _records_by_key(doc, view, options)
    view_tags = ViewTags(doc, view)
    samples = []
    skipped = 0
    for tag in view_tags.tags:
        hosts = compat.tagged_element_ids(tag)
        record = None
        for host_id in hosts:
            record = records.get(host_id)
            if record is not None:
                break
        if record is None:
            skipped += 1
            continue
        try:
            head = compat.xyz_tuple(tag.TagHeadPosition)
        except Exception:
            skipped += 1
            continue
        if head is None:
            skipped += 1
            continue

        head_offset = _view_offset(view, record.point, head)

        # the elbow is kept relative to the *head*, so the leader holds its
        # shape wherever the head ends up - including after decluttering
        elbow_offset = None
        try:
            references = compat.tagged_references(tag)
            if references:
                elbow = compat.get_leader_elbow(tag, references[0])
                if elbow is not None:
                    elbow_view = _view_offset(view, record.point,
                                              compat.xyz_tuple(elbow))
                    elbow_offset = (elbow_view[0] - head_offset[0],
                                    elbow_view[1] - head_offset[1])
        except Exception:
            elbow_offset = None

        axis, host_length = _host_frame(view, record)
        if axis is not None:
            along, across = layout.host_frame_offset(head_offset, axis, host_length)
            placement = layout.Placement(
                tag_type=compat.eid_value(tag.GetTypeId()),
                elbow=elbow_offset,
                orientation=getattr(tag, 'TagOrientation', None),
                has_leader=bool(getattr(tag, 'HasLeader', True)),
                frame=layout.HOST_FRAME, along=along, across=across)
        else:
            placement = layout.Placement(
                tag_type=compat.eid_value(tag.GetTypeId()),
                offset=head_offset, elbow=elbow_offset,
                orientation=getattr(tag, 'TagOrientation', None),
                has_leader=bool(getattr(tag, 'HasLeader', True)))
        samples.append(layout.TagSample(
            signature=record.signature(level), category=record.category,
            order_key=_order_key(view, record.point), placement=placement))
    population = {}
    for record in records.values():
        key = record.signature(level)
        population[key] = population.get(key, 0) + 1
    return layout.learn(samples, population), skipped


class Tagger(object):
    """Applies a learned arrangement to one view. Needs an open transaction."""

    def __init__(self, doc, source_view, target_view, recipe, options, level):
        self.doc = doc
        self.source_view = source_view
        self.target_view = target_view
        self.recipe = recipe
        self.options = options
        self.level = level
        self.scale = self._scale_factor()

    def _scale_factor(self):
        if not self.options.adapt_to_view_scale:
            return 1.0
        try:
            source_scale = float(self.source_view.Scale)
            target_scale = float(self.target_view.Scale)
        except Exception:
            return 1.0
        if source_scale <= 0.0 or target_scale <= 0.0:
            return 1.0
        return target_scale / source_scale

    def blockers(self):
        problems = []
        if (compat.eid_value(self.target_view.Id)
                == compat.eid_value(self.source_view.Id)):
            problems.append('the target view is the source view')
        try:
            if self.target_view.IsTemplate:
                problems.append('the view is a view template')
        except Exception:
            pass
        if isinstance(self.target_view, DB.View3D) and not self._locked():
            problems.append('Revit only allows tags in a locked 3D view - use '
                            '"Save Orientation and Lock View" on it first, or '
                            'switch on "lock 3D views" in the settings')
        return problems

    def _locked(self):
        view = self.target_view
        try:
            if view.IsLocked:
                return True
        except Exception:
            return True
        if not self.options.lock_3d_views:
            return False
        try:
            if view.CanSaveOrientationAndLock():
                view.SaveOrientationAndLock()
                return bool(view.IsLocked)
        except Exception:
            pass
        return False

    # -- step 2: tag what is untagged --------------------------------------

    def _wanted(self, records):
        """Which elements should carry a tag, in reading order.

        Only kinds the reference view actually tagged, and only as many of them
        as it tagged - tagging every pipe when the reference tagged three is
        what turns a clean drawing into a thicket.
        """
        grouped = {}
        for record in records:
            grouped.setdefault(record.signature(self.level), []).append(record)
        wanted = []
        for signature, entries in grouped.items():
            if signature not in self.recipe.by_signature:
                continue
            entries.sort(key=lambda r: layout.sort_key(
                _order_key(self.target_view, r.point)))
            if self.options.match_tag_density:
                count = self.recipe.tags_wanted(signature, len(entries))
            else:
                count = len(entries)
            wanted.extend(entries[:count])
        return wanted

    def tag_untagged(self, records, view_tags, report):
        """Place a tag on every element the reference view would have tagged."""
        created = 0
        for record in self._wanted(records):
            placement, how = self.recipe.placement_for(
                record.signature(self.level), record.category)
            if placement is None:
                continue
            type_id = (placement.tag_type
                       or self.recipe.tag_type_for(record.category))
            if type_id is None:
                continue
            if view_tags.has_tag_of_type(record.key, type_id):
                continue
            element = self.doc.GetElement(compat.to_eid(record.key))
            if element is None:
                continue
            try:
                tag = DB.IndependentTag.Create(
                    self.doc, compat.to_eid(type_id), self.target_view.Id,
                    DB.Reference(element), placement.has_leader,
                    placement.orientation or DB.TagOrientation.Horizontal,
                    compat.to_xyz(record.point))
            except Exception as error:
                report.add(results.ItemResult(
                    TAG_KIND, results.FAILED, record.key,
                    _message(error), None, record.label))
                continue
            if tag is None:
                continue
            view_tags.register(record.key, tag)
            created += 1
        return created

    # -- step 3: arrange ----------------------------------------------------

    def arrange(self, records_by_key, view_tags, report):
        """Move every tag onto the position the reference view implies."""
        hosts = []
        for host_id in view_tags.by_host:
            record = records_by_key.get(host_id)
            if record is None:
                continue
            hosts.append(layout.TargetHost(
                key=host_id, signature=record.signature(self.level),
                category=record.category,
                order_key=_order_key(self.target_view, record.point)))
        assignments = layout.assign(hosts, self.recipe)
        targets = self._targets(assignments, records_by_key, report)

        moved = 0
        self.placed = []
        for assignment in assignments:
            record = records_by_key.get(assignment.key)
            if record is None:
                continue
            if assignment.key not in targets:
                for tag in view_tags.by_host.get(assignment.key, ()):
                    report.add(results.ItemResult(
                        TAG_KIND, results.SKIPPED, compat.eid_value(tag.Id),
                        'the reference view has no tag on this kind of element',
                        None, record.label))
                continue
            for tag in view_tags.by_host.get(assignment.key, ()):
                if self._place(tag, record, targets[assignment.key], report):
                    self.placed.append((tag, record, assignment))
                    moved += 1
        return moved, layout.summarise(assignments)

    def _targets(self, assignments, records_by_key, report):
        """``{host id: (right, up) offset from the host}`` for every tag.

        In margin mode anything with a direction - the pipework, which is what
        crowds a riser - is sent out to a clear band at the side of the drawing
        with a leader back in. Point elements keep the offset the reference view
        gave them: a fixture tag reads better sitting on its fixture, and
        fixtures are not what makes the middle of a riser unreadable.
        """
        wants_margin = (self.options.placement_mode or 'margin').lower() == 'margin'
        targets = {}
        banded = []
        for assignment in assignments:
            record = records_by_key.get(assignment.key)
            if record is None or not assignment.is_guided:
                continue
            axis, host_length = _host_frame(self.target_view, record)
            if wants_margin and axis is not None:
                banded.append((assignment.key,) + _order_key(self.target_view,
                                                             record.point))
                continue
            targets[assignment.key] = assignment.placement.offset_in_view(
                axis, host_length, self.scale)

        if banded:
            gutter = self._paper_to_model(self.options.margin_gutter_inches)
            points = [_order_key(self.target_view, r.point)
                      for r in records_by_key.values()]
            band = margin.band_for(points, gutter)
            _band, placements = margin.plan(banded, gutter, band)
            for placement in placements:
                targets[placement.key] = (placement.position[0] - placement.anchor[0],
                                          placement.position[1] - placement.anchor[1])
            counts = margin.summarise(placements)
            report.note('Margin placement: {0} tag(s) to the left, {1} to the '
                        'right, in a band {2:.2f} ft clear of the drawing'.format(
                            counts.get(margin.LEFT, 0), counts.get(margin.RIGHT, 0),
                            gutter))
        return targets

    def _paper_to_model(self, inches):
        try:
            view_scale = float(self.target_view.Scale)
        except Exception:
            view_scale = 1.0
        if view_scale <= 0.0:
            view_scale = 1.0
        return (inches / 12.0) * view_scale

    def _place(self, tag, record, offset, report):
        """Put one tag at ``offset`` from its element, and fix up its leader."""
        tag_id = None
        try:
            tag_id = compat.eid_value(tag.Id)
        except Exception:
            pass
        try:
            tag.TagHeadPosition = _model_point(self.target_view, record.point,
                                               offset)
        except Exception as error:
            report.add(results.ItemResult(TAG_KIND, results.FAILED, tag_id,
                                          _message(error), None, record.label))
            return False
        # a tag out in the margin is meaningless without something joining it
        # back to the pipe it labels
        if abs(offset[0]) + abs(offset[1]) > 1e-6:
            try:
                tag.HasLeader = True
            except Exception:
                pass
        self._set_elbow(tag, record, offset)
        report.add(results.ItemResult(TAG_KIND, results.CREATED, tag_id,
                                      'placed', tag_id, record.label))
        return True

    def _set_elbow(self, tag, record, offset):
        """A short horizontal run off the tag before the leader turns inward."""
        try:
            references = compat.tagged_references(tag)
        except Exception:
            return
        if not references:
            return
        run = self._paper_to_model(self.options.margin_gutter_inches) * 0.4
        inward = -run if offset[0] > 0 else run
        elbow = (offset[0] + inward, offset[1])
        try:
            compat.set_leader_elbow(
                tag, references[0],
                _model_point(self.target_view, record.point, elbow))
        except Exception:
            pass

def apply_recipe(doc, source_view, target_view, recipe, options, level):
    """Tag and arrange one view. Must be called inside a transaction."""
    report = results.ViewReport(compat.eid_value(target_view.Id),
                                target_view.Name)
    tagger = Tagger(doc, source_view, target_view, recipe, options, level)
    blockers = tagger.blockers()
    if blockers:
        report.aborted = '; '.join(blockers)
        return report

    records_by_key = _records_by_key(doc, target_view, options)
    view_tags = ViewTags(doc, target_view)

    created = 0
    if options.tag_untagged_elements:
        created = tagger.tag_untagged(list(records_by_key.values()),
                                      view_tags, report)
        report.note('Tagged {0} untagged element(s)'.format(created))
    else:
        report.note('Tagging of untagged elements is switched off')

    moved, how = tagger.arrange(records_by_key, view_tags, report)
    report.note('Arranged {0} tag(s)'.format(moved))
    host_framed = sum(1 for placements in recipe.by_signature.values()
                      for p in placements if p.frame == layout.HOST_FRAME)
    report.note('  {0} of {1} learned placements follow the element they label '
                '(the rest are plain offsets)'.format(host_framed,
                                                      recipe.sample_count))
    Declutterer(doc, target_view, options, tagger.scale).run(tagger.placed, report)
    for reason in sorted(how):
        report.note('  {0}: {1}'.format(reason, how[reason]))
    if tagger.scale != 1.0:
        report.note('View scale differs - offsets scaled by {0:.2f}'.format(
            tagger.scale))
    return report


def _message(error):
    text = getattr(error, 'Message', None) or str(error)
    return ' '.join(str(text).split())[:200]


#: a tag's graphic is roughly this much of its text size per character, and
#: this much line height. Rough is fine - it decides spacing, not geometry.
TEXT_WIDTH_FACTOR = 0.62
LINE_HEIGHT_FACTOR = 1.3

#: 3/32" on paper, in feet - Revit's usual default text size
DEFAULT_TEXT_SIZE = 3.0 / 32.0 / 12.0


class Declutterer(object):
    """Measures the placed tags and pushes the overlapping ones apart."""

    def __init__(self, doc, view, options, scale):
        self.doc = doc
        self.view = view
        self.options = options
        self.scale = scale
        self._text_sizes = {}

    def _paper_to_model(self, inches):
        """Inches on the printed sheet, in model feet at this view's scale."""
        return (inches / 12.0) * self._view_scale()

    def _view_scale(self):
        try:
            value = float(self.view.Scale)
        except Exception:
            return 1.0
        return value if value > 0.0 else 1.0

    def _text_size(self, type_id):
        """The tag type's text height in paper feet."""
        key = compat.eid_value(type_id)
        if key in self._text_sizes:
            return self._text_sizes[key]
        size = DEFAULT_TEXT_SIZE
        parameter = compat.builtin('TEXT_SIZE')
        try:
            tag_type = self.doc.GetElement(type_id)
            if tag_type is not None and parameter is not None:
                found = tag_type.get_Parameter(parameter)
                if found is not None and found.HasValue:
                    value = found.AsDouble()
                    if value > 0.0:
                        size = value
        except Exception:
            pass
        self._text_sizes[key] = size
        return size

    def _half_extents(self, tag):
        """Half width and height of the tag's *text*, in model feet.

        Deliberately not ``get_BoundingBox``: a tag's bounding box includes its
        leader, so a tag on a six foot leader measures six feet wide. Feeding
        that to the solver makes every tag look like it collides with every
        other one, and it shoves the whole drawing apart - which is worse than
        the overlap it was trying to fix.
        """
        text = ''
        try:
            text = tag.TagText or ''
        except Exception:
            text = ''
        lines = text.split('\n') if text else ['']
        columns = max(len(line) for line in lines) or 1
        size = self._text_size(tag.GetTypeId()) * self._view_scale()
        return (columns * size * TEXT_WIDTH_FACTOR / 2.0,
                len(lines) * size * LINE_HEIGHT_FACTOR / 2.0)

    def run(self, placed, report):
        if not self.options.declutter_tags or len(placed) < 2:
            return None
        try:
            self.doc.Regenerate()
        except Exception:
            pass

        right, up, _ = compat.view_axes(self.view)
        labels = []
        by_key = {}
        for tag, record, assignment in placed:
            try:
                head = compat.xyz_tuple(tag.TagHeadPosition)
            except Exception:
                continue
            if head is None:
                continue
            half_width, half_height = self._half_extents(tag)
            key = compat.eid_value(tag.Id)
            labels.append(declutter.Label(
                key=key,
                desired=(geom.dot(head, right), geom.dot(head, up)),
                half_width=max(half_width, 1e-4),
                half_height=max(half_height, 1e-4),
                anchor=(geom.dot(record.point, right), geom.dot(record.point, up))))
            by_key[key] = (tag, head)

        if len(labels) < 2:
            return None

        # A tag beside its element must not wander far, or it stops reading as
        # belonging to it. A tag already sent out to the margin is a different
        # matter: stacking the column *is* the placement, and a column of thirty
        # needs far more room than that limit allows.
        if (self.options.placement_mode or 'margin').lower() == 'margin':
            max_shift = None
        else:
            max_shift = self._paper_to_model(
                self.options.declutter_max_shift_inches)

        result = declutter.resolve(
            labels,
            gap=self._paper_to_model(self.options.declutter_gap_inches),
            iterations=int(self.options.declutter_passes),
            max_shift=max_shift)

        nudged = 0
        for label in result.labels:
            shift = label.shift
            if abs(shift[0]) < 1e-9 and abs(shift[1]) < 1e-9:
                continue
            tag, head = by_key[label.key]
            try:
                tag.TagHeadPosition = compat.to_xyz(
                    geom.add(head, geom.add(geom.scale(right, shift[0]),
                                            geom.scale(up, shift[1]))))
                nudged += 1
            except Exception:
                continue
        report.note('Decluttering: {0} (gap {1:.2f} ft, limit {2} at this '
                    'scale)'.format(
                        result.summary(),
                        self._paper_to_model(self.options.declutter_gap_inches),
                        'none' if max_shift is None
                        else '{0:.2f} ft'.format(max_shift)))
        if result.remaining_overlaps:
            report.note('  {0} tag(s) could not be separated without moving '
                        'further than the limit - raise "max shift" in the '
                        'settings, or move them by hand'.format(
                            result.remaining_overlaps))
        return result
