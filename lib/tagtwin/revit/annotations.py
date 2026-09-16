# -*- coding: utf-8 -*-
"""Read the annotations of one view and rebuild them in another.

Two families of annotation, handled differently:

*Referencing* annotations - tags, dimensions, spot dimensions - point at model
elements. They are rebuilt from scratch against the **matched** element, which
is the whole point of the tool: a plain copy would leave them pointing at the
original suite's elements (or go blank).

*Free* annotations - text, detail lines, regions, symbols - only have geometry.
They are re-created at the transformed position. They are re-created rather than
copied so that text in a mirrored suite reads forwards instead of backwards.

Every handler is wrapped: one annotation that Revit refuses is recorded in the
report and the run carries on.
"""

from __future__ import division

import math

from Autodesk.Revit import DB

from tagtwin import geom, results
from tagtwin.revit import compat, refs
from tagtwin.signature import LOOSE, ElementRecord
from tagtwin.spatial import PointIndex

KIND_TAG = 'Tag'
KIND_ROOM_TAG = 'Room/space tag'
KIND_DIMENSION = 'Dimension'
KIND_SPOT = 'Spot dimension'
KIND_TEXT = 'Text note'
KIND_DETAIL_CURVE = 'Detail line'
KIND_REGION = 'Filled region'
KIND_SYMBOL = 'Annotation symbol'
KIND_CLOUD = 'Revision cloud'

#: which option switches each kind off
KIND_OPTION = {
    KIND_TAG: 'copy_tags',
    KIND_ROOM_TAG: 'copy_tags',
    KIND_DIMENSION: 'copy_dimensions',
    KIND_SPOT: 'copy_spot_dimensions',
    KIND_TEXT: 'copy_text',
    KIND_DETAIL_CURVE: 'copy_detail_lines',
    KIND_REGION: 'copy_regions',
    KIND_SYMBOL: 'copy_symbols',
    KIND_CLOUD: 'copy_regions',
}

#: view machinery that lives in a view but must never be duplicated into another
EXCLUDED_CATEGORY_NAMES = (
    'OST_Viewers', 'OST_Callouts', 'OST_CalloutHeads', 'OST_CropBoundary',
    'OST_MatchlineAxis', 'OST_ReferenceViewer', 'OST_SectionLine',
    'OST_SectionHeads', 'OST_Elev', 'OST_ElevationMarks', 'OST_Sections',
    'OST_Viewports', 'OST_TitleBlocks', 'OST_Sheets', 'OST_ScheduleGraphics',
    'OST_ColorFillLegends', 'OST_RasterImages', 'OST_Constraints',
)


def _excluded_category_ids():
    values = set()
    for name in EXCLUDED_CATEGORY_NAMES:
        category = getattr(DB.BuiltInCategory, name, None)
        if category is not None:
            try:
                values.add(int(category))
            except Exception:
                pass
    return values


def _spatial_tag_types():
    types = []
    for holder, name in ((getattr(DB, 'Architecture', None), 'RoomTag'),
                         (getattr(DB, 'Mechanical', None), 'SpaceTag'),
                         (DB, 'AreaTag')):
        if holder is None:
            continue
        tag_type = getattr(holder, name, None)
        if tag_type is not None:
            types.append(tag_type)
    return tuple(types)


SPATIAL_TAG_TYPES = _spatial_tag_types()


class AnnotationItem(object):
    """One source annotation, with the model elements it depends on."""

    __slots__ = ('kind', 'element', 'element_id', 'host_ids', 'label')

    def __init__(self, kind, element, element_id, host_ids, label=''):
        self.kind = kind
        self.element = element
        self.element_id = element_id
        self.host_ids = host_ids
        self.label = label

    @property
    def references_model(self):
        return self.kind in (KIND_TAG, KIND_ROOM_TAG, KIND_DIMENSION, KIND_SPOT)

    def __repr__(self):
        return '<AnnotationItem {0} {1}>'.format(self.kind, self.element_id)


def classify(element):
    """Which handler an annotation belongs to, or ``None`` if unsupported."""
    if isinstance(element, DB.IndependentTag):
        return KIND_TAG
    if SPATIAL_TAG_TYPES and isinstance(element, SPATIAL_TAG_TYPES):
        return KIND_ROOM_TAG
    if isinstance(element, DB.SpotDimension):      # before Dimension - subclass
        return KIND_SPOT
    if isinstance(element, DB.Dimension):
        return KIND_DIMENSION
    if isinstance(element, DB.TextNote):
        return KIND_TEXT
    if isinstance(element, DB.DetailCurve):
        return KIND_DETAIL_CURVE
    if isinstance(element, DB.FilledRegion):
        return KIND_REGION
    if isinstance(element, DB.RevisionCloud):
        return KIND_CLOUD
    if isinstance(element, DB.FamilyInstance):
        return KIND_SYMBOL
    return None


def _host_ids(element, kind):
    if kind == KIND_TAG:
        return compat.tagged_element_ids(element)
    if kind == KIND_ROOM_TAG:
        for name in ('Room', 'Space', 'Area'):
            spatial = getattr(element, name, None)
            if spatial is not None:
                value = compat.eid_value(spatial.Id)
                return [value] if value else []
        return []
    if kind in (KIND_DIMENSION, KIND_SPOT):
        found = []
        try:
            for reference in element.References:
                value = refs.reference_element_id(reference)
                if value is not None and value > 0 and value not in found:
                    found.append(value)
        except Exception:
            pass
        return found
    return []


def collect_annotations(doc, view, options):
    """``(items, unsupported)`` for every annotation owned by ``view``."""
    excluded = _excluded_category_ids()
    items = []
    unsupported = []
    view_id = compat.eid_value(view.Id)
    collector = DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    for element in collector:
        try:
            if not element.ViewSpecific:
                continue
            if compat.eid_value(element.OwnerViewId) != view_id:
                continue
            category = element.Category
            if category is None:
                continue
            if compat.eid_value(category.Id) in excluded:
                continue
        except Exception:
            continue

        kind = classify(element)
        element_id = compat.eid_value(element.Id)
        if kind is None:
            unsupported.append(results.ItemResult(
                category.Name or 'Other', results.SKIPPED, element_id,
                'Tag Twin cannot rebuild this kind of annotation'))
            continue
        if not getattr(options, KIND_OPTION.get(kind, ''), True):
            continue
        items.append(AnnotationItem(kind, element, element_id,
                                    _host_ids(element, kind), category.Name))
    return items, unsupported


class Replicator(object):
    """Rebuilds a view's annotations in another view. Needs an open transaction."""

    def __init__(self, doc, source_view, target_view, solve_result, options):
        self.doc = doc
        self.source_view = source_view
        self.target_view = target_view
        self.options = options
        self.solve_result = solve_result
        self.match_result = solve_result.match_result
        self.alignment = self.match_result.alignment
        self.id_map = self.match_result.id_map
        self.match_map = self.match_result.match_map
        self.scale = self._scale_factor()
        self.offset_mode = self._offset_mode()
        self._transform = compat.to_transform(self.alignment)
        self._existing_tags = None
        self._existing_index = None
        self._handlers = {
            KIND_TAG: self._create_tag,
            KIND_ROOM_TAG: self._create_spatial_tag,
            KIND_DIMENSION: self._create_dimension,
            KIND_SPOT: self._create_spot_dimension,
            KIND_TEXT: self._create_text_note,
            KIND_DETAIL_CURVE: self._create_detail_curve,
            KIND_REGION: self._create_filled_region,
            KIND_SYMBOL: self._create_symbol,
            KIND_CLOUD: self._create_revision_cloud,
        }

    # -- placement --------------------------------------------------------

    def _scale_factor(self):
        """Annotation offsets are model distances, so they follow the view scale."""
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

    def _offset_mode(self):
        mode = (self.options.offset_mode or 'auto').lower()
        if mode not in ('auto', 'model', 'view'):
            mode = 'auto'
        if mode == 'auto':
            # looking the same way: keep offsets in model space, which is exact.
            # looking different ways: keep them in view space, so the annotation
            # sits where it looks like it should on the sheet.
            return 'model' if compat.views_are_parallel(
                self.source_view, self.target_view) else 'view'
        return mode

    def _anchor(self, host_ids):
        for host_id in host_ids or ():
            match = self.match_map.get(host_id)
            if match is not None:
                return match.source.point, match.target.point
        return None, None

    def _to_target_view_axes(self, offset):
        source_right, source_up, source_direction = compat.view_axes(self.source_view)
        target_right, target_up, target_direction = compat.view_axes(self.target_view)
        across = geom.dot(offset, source_right)
        up = geom.dot(offset, source_up)
        depth = geom.dot(offset, source_direction)
        return geom.add(geom.add(geom.scale(target_right, across),
                                 geom.scale(target_up, up)),
                        geom.scale(target_direction, depth))

    def place(self, point, host_ids=None):
        """Where a source annotation point belongs in the target view.

        When the annotation has a matched host, the point is kept at the same
        offset *from that host* rather than at the transformed absolute
        position. Small differences between the two suites then move the tag
        with its element instead of leaving it stranded.
        """
        raw = compat.xyz_tuple(point)
        if raw is None:
            return None
        source_anchor, target_anchor = self._anchor(host_ids)
        if source_anchor is None or not self.options.rehost_to_matched_point:
            return compat.to_xyz(self.alignment.apply(raw))
        offset = geom.sub(raw, source_anchor)
        if self.offset_mode == 'view':
            offset = self._to_target_view_axes(offset)
        else:
            offset = self.alignment.apply_vector(offset)
        if self.scale != 1.0:
            offset = geom.scale(offset, self.scale)
        return compat.to_xyz(geom.add(target_anchor, offset))

    def place_free(self, point):
        raw = compat.xyz_tuple(point)
        if raw is None:
            return None
        return compat.to_xyz(self.alignment.apply(raw))

    def _transform_curve(self, curve):
        try:
            return curve.CreateTransformed(self._transform)
        except Exception:
            pass
        # mirrored transforms can be refused - rebuild straight curves by hand
        try:
            start = self.place_free(curve.GetEndPoint(0))
            end = self.place_free(curve.GetEndPoint(1))
            return DB.Line.CreateBound(start, end)
        except Exception:
            return None

    def _view_angle(self, view, direction):
        right, up, _ = compat.view_axes(view)
        return math.atan2(geom.dot(direction, up), geom.dot(direction, right))

    # -- duplicate guards -------------------------------------------------

    def _existing_tag_keys(self):
        """``(tag type, tagged element)`` pairs already present in the target."""
        if self._existing_tags is None:
            keys = set()
            collector = DB.FilteredElementCollector(self.doc, self.target_view.Id)
            for tag in collector.OfClass(DB.IndependentTag):
                type_id = compat.eid_value(tag.GetTypeId())
                for host_id in compat.tagged_element_ids(tag):
                    keys.add((type_id, host_id))
            self._existing_tags = keys
        return self._existing_tags

    def _existing_annotation_index(self):
        """Free annotations already in the target view, indexed by position."""
        if self._existing_index is None:
            records = []
            collector = DB.FilteredElementCollector(
                self.doc, self.target_view.Id).WhereElementIsNotElementType()
            for element in collector:
                try:
                    if not element.ViewSpecific:
                        continue
                    kind = classify(element)
                    if kind is None or kind in (KIND_TAG, KIND_ROOM_TAG):
                        continue
                    point = self._position_of(element)
                    if point is None:
                        continue
                    records.append(ElementRecord(
                        key=compat.eid_value(element.Id), category=kind,
                        type_id=compat.eid_value(element.GetTypeId()), point=point))
                except Exception:
                    continue
            tolerance = max(self.options.position_tolerance, 0.02)
            # LOOSE, so the index key is (kind, type) - what _already_there asks for
            self._existing_index = PointIndex(records, LOOSE, tolerance)
        return self._existing_index

    def _position_of(self, element):
        try:
            location = element.Location
            if isinstance(location, DB.LocationPoint):
                return compat.xyz_tuple(location.Point)
            if isinstance(location, DB.LocationCurve):
                return compat.xyz_tuple(location.Curve.GetEndPoint(0))
        except Exception:
            pass
        for name in ('Coord', 'Origin'):
            try:
                value = getattr(element, name, None)
                if value is not None:
                    return compat.xyz_tuple(value)
            except Exception:
                continue
        try:
            box = element.get_BoundingBox(self.target_view)
            if box is not None:
                return geom.scale(geom.add(compat.xyz_tuple(box.Min),
                                           compat.xyz_tuple(box.Max)), 0.5)
        except Exception:
            pass
        return None

    def _already_there(self, kind, type_id, point):
        if not self.options.skip_existing or point is None:
            return False
        index = self._existing_annotation_index()
        tolerance = max(self.options.position_tolerance, 0.02)
        signature = (kind, compat.eid_value(type_id))
        return index.nearest(signature, compat.xyz_tuple(point), tolerance) is not None

    # -- running ----------------------------------------------------------

    def blockers(self, items):
        """Reasons this target view cannot be written to, as a list of strings."""
        problems = []
        if compat.eid_value(self.target_view.Id) == compat.eid_value(self.source_view.Id):
            problems.append('the target view is the source view')
        try:
            if self.target_view.IsTemplate:
                problems.append('the view is a view template')
        except Exception:
            pass
        needs_tags = any(item.references_model for item in items)
        if needs_tags and isinstance(self.target_view, DB.View3D):
            if not self._ensure_3d_view_locked():
                problems.append('Revit only allows tags and dimensions in a '
                                'locked 3D view - use "Save Orientation and '
                                'Lock View" on it first, or switch on "lock 3D '
                                'views" in the settings')
        return problems

    def _ensure_3d_view_locked(self):
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

    def run(self, items, report):
        for item in items:
            handler = self._handlers.get(item.kind)
            if handler is None:
                report.add(results.ItemResult(item.kind, results.SKIPPED,
                                              item.element_id, 'unsupported'))
                continue
            try:
                report.add(handler(item))
            except Exception as error:
                report.add(self._failed(item, _message(error)))
        return report

    def _created(self, item, element, message=''):
        new_id = None
        try:
            new_id = compat.eid_value(element.Id)
        except Exception:
            pass
        return results.ItemResult(item.kind, results.CREATED, item.element_id,
                                  message, new_id, item.label)

    def _skipped(self, item, message):
        return results.ItemResult(item.kind, results.SKIPPED, item.element_id,
                                  message, None, item.label)

    def _failed(self, item, message):
        return results.ItemResult(item.kind, results.FAILED, item.element_id,
                                  message, None, item.label)

    # -- handlers: referencing annotations --------------------------------

    def _create_tag(self, item):
        source = item.element
        references = compat.tagged_references(source)
        if not references:
            return self._skipped(item, 'the tag points at nothing')
        mapped, unmapped = refs.remap_all(self.doc, references, self.id_map,
                                          allow_element_fallback=True)
        if not mapped:
            return self._skipped(item, 'the tagged element has no twin in this view')

        type_id = source.GetTypeId()
        if self.options.skip_existing:
            existing = self._existing_tag_keys()
            type_value = compat.eid_value(type_id)
            hosts = [self.id_map.get(h) for h in item.host_ids]
            hosts = [h for h in hosts if h is not None]
            if hosts and all((type_value, h) in existing for h in hosts):
                return self._skipped(item, 'the same tag is already on that element')

        head = self.place(source.TagHeadPosition, item.host_ids)
        tag = DB.IndependentTag.Create(self.doc, type_id, self.target_view.Id,
                                       mapped[0][1], source.HasLeader,
                                       source.TagOrientation, head)
        if tag is None:
            return self._failed(item, 'Revit did not create the tag')
        if len(mapped) > 1:
            try:
                tag.AddReferences(compat.net_list(
                    DB.Reference, [pair[1] for pair in mapped[1:]]))
            except Exception:
                pass
        self._copy_leader(source, tag, mapped, item)
        try:
            tag.TagHeadPosition = head
        except Exception:
            pass
        if self._existing_tags is not None:
            for host_id in item.host_ids:
                mapped_host = self.id_map.get(host_id)
                if mapped_host is not None:
                    self._existing_tags.add((compat.eid_value(type_id), mapped_host))
        message = ''
        if unmapped:
            message = 'tagged {0} of {1} elements'.format(
                len(mapped), len(mapped) + len(unmapped))
        return self._created(item, tag, message)

    def _copy_leader(self, source, tag, mapped, item):
        if not source.HasLeader:
            return
        try:
            tag.LeaderEndCondition = source.LeaderEndCondition
        except Exception:
            pass
        free_end = False
        try:
            free_end = tag.LeaderEndCondition == DB.LeaderEndCondition.Free
        except Exception:
            pass
        for source_reference, target_reference in mapped:
            elbow = compat.get_leader_elbow(source, source_reference)
            if elbow is not None:
                compat.set_leader_elbow(tag, target_reference,
                                        self.place(elbow, item.host_ids))
            if free_end:
                end = compat.get_leader_end(source, source_reference)
                if end is not None:
                    compat.set_leader_end(tag, target_reference,
                                          self.place(end, item.host_ids))

    def _create_spatial_tag(self, item):
        source = item.element
        if not item.host_ids:
            return self._skipped(item, 'the tag is not placed in a room or space')
        target_host = self.id_map.get(item.host_ids[0])
        if target_host is None:
            return self._skipped(item, 'the tagged room/space has no twin in this view')
        point = self.place(self._position_of(source), item.host_ids)
        if point is None:
            return self._skipped(item, 'the tag has no position')
        link_id = DB.LinkElementId(compat.to_eid(target_host))
        creator = self.doc.Create
        if isinstance(source, getattr(getattr(DB, 'Mechanical', None), 'SpaceTag', ())):
            space = self.doc.GetElement(compat.to_eid(target_host))
            tag = creator.NewSpaceTag(space, DB.UV(point.X, point.Y), self.target_view)
        else:
            tag = creator.NewRoomTag(link_id, DB.UV(point.X, point.Y),
                                     self.target_view.Id)
        if tag is None:
            return self._failed(item, 'Revit did not create the tag')
        try:
            tag.ChangeTypeId(source.GetTypeId())
        except Exception:
            pass
        try:
            tag.TagHeadPosition = point
        except Exception:
            pass
        return self._created(item, tag)

    def _create_dimension(self, item):
        source = item.element
        try:
            references = list(source.References)
        except Exception:
            references = []
        if len(references) < 2:
            return self._skipped(item, 'the dimension has fewer than two references')
        mapped, unmapped = refs.remap_all(self.doc, references, self.id_map,
                                          allow_element_fallback=False)
        if unmapped:
            return self._skipped(
                item, 'could not re-point {0} of {1} dimension references'.format(
                    len(unmapped), len(references)))
        line = self._dimension_line(source)
        if line is None:
            return self._skipped(item, 'only straight dimensions can be rebuilt')
        dimension_type = self.doc.GetElement(source.GetTypeId())
        array = DB.ReferenceArray()
        for _, target_reference in mapped:
            array.Append(target_reference)
        dimension = self.doc.Create.NewDimension(self.target_view, line, array,
                                                 dimension_type)
        if dimension is None:
            return self._failed(item, 'Revit did not create the dimension')
        self._copy_dimension_text(source, dimension)
        return self._created(item, dimension)

    def _dimension_line(self, source):
        try:
            curve = source.Curve
        except Exception:
            curve = None
        if curve is None:
            return None
        try:
            if not curve.IsBound:
                origin = compat.xyz_tuple(curve.Origin)
                direction = compat.xyz_tuple(curve.Direction)
                curve = DB.Line.CreateBound(
                    compat.to_xyz(geom.sub(origin, geom.scale(direction, 5.0))),
                    compat.to_xyz(geom.add(origin, geom.scale(direction, 5.0))))
        except Exception:
            pass
        if not isinstance(curve, DB.Line):
            return None
        transformed = self._transform_curve(curve)
        return transformed if isinstance(transformed, DB.Line) else None

    def _copy_dimension_text(self, source, target):
        for name in ('Prefix', 'Suffix', 'Above', 'Below', 'ValueOverride'):
            try:
                value = getattr(source, name)
            except Exception:
                continue
            if not value:
                continue
            try:
                setattr(target, name, value)
            except Exception:
                pass
        try:
            source_segments = list(source.Segments)
            target_segments = list(target.Segments)
        except Exception:
            return
        for index, source_segment in enumerate(source_segments):
            if index >= len(target_segments):
                break
            for name in ('Prefix', 'Suffix', 'Above', 'Below', 'ValueOverride'):
                try:
                    value = getattr(source_segment, name)
                    if value:
                        setattr(target_segments[index], name, value)
                except Exception:
                    pass

    def _create_spot_dimension(self, item):
        source = item.element
        try:
            references = list(source.References)
        except Exception:
            references = []
        mapped, _ = refs.remap_all(self.doc, references, self.id_map,
                                   allow_element_fallback=False)
        if not mapped:
            return self._skipped(item, 'the measured element has no twin in this view')

        origin = self.place(_first_attribute(source, ('Origin',)), item.host_ids)
        if origin is None:
            return self._skipped(item, 'the spot dimension has no origin')
        bend = self.place(_first_attribute(source, ('LeaderShoulderPosition',
                                                    'TextPosition')), item.host_ids)
        end = self.place(_first_attribute(source, ('LeaderEndPosition',
                                                   'TextPosition')), item.host_ids)
        if bend is None:
            bend = origin
        if end is None:
            end = bend
        has_leader = bool(_first_attribute(source, ('LeaderHasShoulder', 'HasLeader')))
        creator = self.doc.Create
        coordinate = _is_category(source, 'OST_SpotCoordinates')
        maker = creator.NewSpotCoordinate if coordinate else creator.NewSpotElevation
        spot = maker(self.target_view, mapped[0][1], origin, bend, end,
                     origin, has_leader)
        if spot is None:
            return self._failed(item, 'Revit did not create the spot dimension')
        try:
            spot.ChangeTypeId(source.GetTypeId())
        except Exception:
            pass
        return self._created(item, spot)

    # -- handlers: free annotations ---------------------------------------

    def _create_text_note(self, item):
        source = item.element
        point = self.place_free(_first_attribute(source, ('Coord',)))
        if point is None:
            return self._skipped(item, 'the text note has no position')
        if self._already_there(KIND_TEXT, source.GetTypeId(), point):
            return self._skipped(item, 'the same text is already there')

        note_options = DB.TextNoteOptions(source.GetTypeId())
        for name in ('HorizontalAlignment', 'KeepRotatedTextReadable'):
            try:
                setattr(note_options, name, getattr(source, name))
            except Exception:
                pass
        try:
            note_options.Rotation = self._text_rotation(source)
        except Exception:
            pass

        width = None
        try:
            width = float(source.Width) * self.scale
        except Exception:
            width = None
        if width and width > 0.0:
            note = DB.TextNote.Create(self.doc, self.target_view.Id, point,
                                      width, source.Text, note_options)
        else:
            note = DB.TextNote.Create(self.doc, self.target_view.Id, point,
                                      source.Text, note_options)
        if note is None:
            return self._failed(item, 'Revit did not create the text note')
        try:
            note.SetFormattedText(source.GetFormattedText())
        except Exception:
            pass
        message = self._copy_text_leaders(source, note)
        return self._created(item, note, message)

    def _text_rotation(self, source):
        direction = compat.xyz_tuple(source.BaseDirection)
        if direction is None:
            return 0.0
        if self.offset_mode == 'view':
            return self._view_angle(self.source_view, direction)
        return self._view_angle(self.target_view,
                                self.alignment.apply_vector(direction))

    def _copy_text_leaders(self, source, note):
        try:
            source_leaders = list(source.GetLeaders())
        except Exception:
            return ''
        if not source_leaders:
            return ''
        right, up, _ = compat.view_axes(self.target_view)
        origin = compat.xyz_tuple(note.Coord)
        added = 0
        for leader in source_leaders:
            try:
                end = self.place_free(leader.End)
                if end is None:
                    continue
                side = geom.dot(geom.sub(compat.xyz_tuple(end), origin), right)
                style = _leader_style(side)
                if style is None:
                    continue
                new_leader = note.AddLeader(style)
                new_leader.End = end
                elbow = self.place_free(leader.Elbow)
                if elbow is not None:
                    new_leader.Elbow = elbow
                added += 1
            except Exception:
                continue
        if added < len(source_leaders):
            return 'copied {0} of {1} leaders'.format(added, len(source_leaders))
        return ''

    def _create_detail_curve(self, item):
        source = item.element
        curve = self._transform_curve(source.GeometryCurve)
        if curve is None:
            return self._skipped(item, 'the curve could not be transformed')
        if self._already_there(KIND_DETAIL_CURVE, source.GetTypeId(),
                               curve.GetEndPoint(0)):
            return self._skipped(item, 'the same detail line is already there')
        element = self.doc.Create.NewDetailCurve(self.target_view, curve)
        if element is None:
            return self._failed(item, 'Revit did not create the detail line')
        try:
            element.LineStyle = source.LineStyle
        except Exception:
            pass
        return self._created(item, element)

    def _create_filled_region(self, item):
        source = item.element
        try:
            loops = list(source.GetBoundaries())
        except Exception:
            loops = []
        if not loops:
            return self._skipped(item, 'the region has no boundary')
        transformed = []
        for loop in loops:
            try:
                transformed.append(DB.CurveLoop.CreateViaTransform(loop, self._transform))
            except Exception:
                return self._skipped(item, 'the boundary could not be transformed')
        region = DB.FilledRegion.Create(
            self.doc, source.GetTypeId(), self.target_view.Id,
            compat.net_list(DB.CurveLoop, transformed))
        if region is None:
            return self._failed(item, 'Revit did not create the filled region')
        return self._created(item, region)

    def _create_symbol(self, item):
        source = item.element
        location = getattr(source, 'Location', None)
        if not isinstance(location, DB.LocationPoint):
            return self._skipped(item, 'the symbol has no insertion point')
        point = self.place_free(location.Point)
        symbol = source.Symbol
        if self._already_there(KIND_SYMBOL, symbol.Id, point):
            return self._skipped(item, 'the same symbol is already there')
        if not symbol.IsActive:
            symbol.Activate()
        instance = self.doc.Create.NewFamilyInstance(point, symbol, self.target_view)
        if instance is None:
            return self._failed(item, 'Revit did not create the symbol')
        self._match_symbol_rotation(source, instance, point)
        self._copy_instance_parameters(source, instance)
        return self._created(item, instance)

    def _match_symbol_rotation(self, source, instance, point):
        try:
            source_rotation = source.Location.Rotation
        except Exception:
            return
        wanted = source_rotation
        if self.offset_mode != 'view':
            if self.alignment.mirror:
                wanted = -wanted
            wanted += self.alignment.angle
        try:
            current = instance.Location.Rotation
        except Exception:
            current = 0.0
        delta = wanted - current
        if abs(delta) < 1e-9:
            return
        try:
            direction = self.target_view.ViewDirection
            axis = DB.Line.CreateBound(point, point + direction)
            DB.ElementTransformUtils.RotateElement(self.doc, instance.Id, axis, delta)
        except Exception:
            pass

    def _copy_instance_parameters(self, source, target):
        for parameter in source.Parameters:
            try:
                if parameter.IsReadOnly or not parameter.HasValue:
                    continue
                definition = parameter.Definition
                if definition is None:
                    continue
                twin = target.LookupParameter(definition.Name)
                if twin is None or twin.IsReadOnly:
                    continue
                if twin.StorageType != parameter.StorageType:
                    continue
                if parameter.StorageType == DB.StorageType.String:
                    twin.Set(parameter.AsString() or '')
                elif parameter.StorageType == DB.StorageType.Double:
                    twin.Set(parameter.AsDouble())
                elif parameter.StorageType == DB.StorageType.Integer:
                    twin.Set(parameter.AsInteger())
            except Exception:
                continue

    def _create_revision_cloud(self, item):
        source = item.element
        curves = None
        for name in ('GetSketchCurves', 'GetCurves'):
            getter = getattr(source, name, None)
            if getter is None:
                continue
            try:
                curves = list(getter())
                break
            except Exception:
                continue
        if not curves:
            return self._skipped(item, 'the cloud sketch could not be read')
        transformed = []
        for curve in curves:
            moved = self._transform_curve(curve)
            if moved is None:
                return self._skipped(item, 'the cloud sketch could not be transformed')
            transformed.append(moved)
        cloud = DB.RevisionCloud.Create(self.doc, self.target_view, source.RevisionId,
                                        compat.net_list(DB.Curve, transformed))
        if cloud is None:
            return self._failed(item, 'Revit did not create the revision cloud')
        return self._created(item, cloud)


def _first_attribute(element, names):
    for name in names:
        try:
            value = getattr(element, name, None)
        except Exception:
            continue
        if value is not None:
            return value
    return None


def _is_category(element, builtin_name):
    category = getattr(DB.BuiltInCategory, builtin_name, None)
    if category is None:
        return False
    try:
        return compat.eid_value(element.Category.Id) == int(category)
    except Exception:
        return False


def _leader_style(side):
    """Left or right straight leader, depending on which way the leader points."""
    name = 'TNLT_STRAIGHT_L' if side < 0 else 'TNLT_STRAIGHT_R'
    style = getattr(DB.TextNoteLeaderTypes, name, None)
    if style is None:
        style = getattr(DB.TextNoteLeaderTypes, 'TNLT_STRAIGHT_R', None)
    return style


def _message(error):
    text = getattr(error, 'Message', None) or str(error)
    text = ' '.join(str(text).split())
    return text[:200]
