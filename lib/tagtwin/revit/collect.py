# -*- coding: utf-8 -*-
"""Read the model elements of a view into transform-independent records."""

from __future__ import division

from Autodesk.Revit import DB

from tagtwin import geom
from tagtwin.revit import compat
from tagtwin.signature import ElementRecord, classify_direction, quantize

#: datums, views and containers - visible in a view, but never tagged as such
EXCLUDED_CATEGORY_NAMES = (
    'OST_Cameras', 'OST_SectionBox', 'OST_Viewers', 'OST_RvtLinks',
    'OST_IOSModelGroups', 'OST_Levels', 'OST_Grids', 'OST_VolumeOfInterest',
    'OST_ProjectBasePoint', 'OST_SharedBasePoint', 'OST_SurveyPoint',
    'OST_Coordination_Model', 'OST_Sun', 'OST_SunStudy', 'OST_ReferencePoints',
)

#: instance parameters worth putting in a signature, per discipline
SIZE_PARAMETERS = (
    'RBS_PIPE_DIAMETER_PARAM',
    'RBS_CURVE_DIAMETER_PARAM',
    'RBS_CURVE_WIDTH_PARAM',
    'RBS_CURVE_HEIGHT_PARAM',
    'RBS_CABLETRAY_WIDTH_PARAM',
    'RBS_CABLETRAY_HEIGHT_PARAM',
    'RBS_CONDUIT_DIAMETER_PARAM',
)

SYSTEM_PARAMETERS = (
    'RBS_PIPING_SYSTEM_TYPE_PARAM',
    'RBS_DUCT_SYSTEM_TYPE_PARAM',
    'RBS_SYSTEM_CLASSIFICATION_PARAM',
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


class RecordBuilder(object):
    """Builds :class:`~tagtwin.signature.ElementRecord` objects from elements.

    Type names and built-in parameter lookups are cached: a view with ten
    thousand pipes has perhaps a dozen distinct types between them.
    """

    def __init__(self, doc, options):
        self.doc = doc
        self.options = options
        self.excluded = _excluded_category_ids()
        self._type_names = {}
        self._size_parameters = [compat.builtin(n) for n in SIZE_PARAMETERS]
        self._size_parameters = [p for p in self._size_parameters if p is not None]
        self._system_parameters = [compat.builtin(n) for n in SYSTEM_PARAMETERS]
        self._system_parameters = [p for p in self._system_parameters if p is not None]

    # -- geometry ---------------------------------------------------------

    def _placement(self, element):
        """``(point, axis, length)`` for an element, or ``(None, None, None)``."""
        try:
            location = element.Location
        except Exception:
            location = None

        if isinstance(location, DB.LocationCurve):
            try:
                curve = location.Curve
                start = compat.xyz_tuple(curve.GetEndPoint(0))
                end = compat.xyz_tuple(curve.GetEndPoint(1))
                middle = compat.xyz_tuple(curve.Evaluate(0.5, True))
                return middle, geom.sub(end, start), curve.Length
            except Exception:
                pass
        elif isinstance(location, DB.LocationPoint):
            try:
                return compat.xyz_tuple(location.Point), None, None
            except Exception:
                pass

        try:
            box = element.get_BoundingBox(None)
        except Exception:
            box = None
        if box is None:
            return None, None, None
        minimum = compat.xyz_tuple(box.Min)
        maximum = compat.xyz_tuple(box.Max)
        centre = geom.scale(geom.add(minimum, maximum), 0.5)
        return centre, None, None

    def _size(self, element):
        """A rotation-independent size fingerprint.

        MEP sizes come from parameters. Everything else falls back to the
        bounding box, sorted so that the same element rotated by a right angle
        still fingerprints the same.
        """
        quantum = self.options.size_quantum
        values = []
        for parameter in self._size_parameters:
            value = compat.param_double(element, parameter)
            if value is not None and value > 0.0:
                values.append(quantize(value, quantum))
        if values:
            return tuple(values)
        try:
            box = element.get_BoundingBox(None)
        except Exception:
            box = None
        if box is None:
            return None
        extents = sorted(abs(box.Max[i] - box.Min[i]) for i in range(3))
        return tuple(quantize(e, max(quantum, 0.01)) for e in extents)

    def _system_id(self, element):
        for parameter in self._system_parameters:
            value = compat.param_eid_value(element, parameter)
            if value is not None and value > 0:
                return value
        try:
            system = element.MEPSystem
            if system is not None:
                return compat.eid_value(system.GetTypeId())
        except Exception:
            pass
        return 0

    def _type_name(self, element, type_id):
        key = compat.eid_value(type_id)
        if key in self._type_names:
            return self._type_names[key]
        name = ''
        try:
            element_type = self.doc.GetElement(type_id)
            if element_type is not None:
                family = getattr(element_type, 'FamilyName', '') or ''
                name = '{0} : {1}'.format(family, DB.Element.Name.GetValue(element_type))
        except Exception:
            name = ''
        if not name.strip(' :'):
            try:
                name = DB.Element.Name.GetValue(element)
            except Exception:
                name = ''
        self._type_names[key] = name
        return name

    # -- records ----------------------------------------------------------

    def is_candidate(self, element):
        try:
            if element.ViewSpecific:
                return False
            category = element.Category
            if category is None:
                return False
            if category.CategoryType != DB.CategoryType.Model:
                return False
            if compat.eid_value(category.Id) in self.excluded:
                return False
        except Exception:
            return False
        return True

    def build(self, element):
        point, axis, length = self._placement(element)
        if point is None:
            return None
        type_id = element.GetTypeId()
        quantum = self.options.size_quantum
        try:
            category_name = element.Category.Name
            category_id = compat.eid_value(element.Category.Id)
        except Exception:
            return None
        return ElementRecord(
            key=compat.eid_value(element.Id),
            category=category_id,
            type_id=compat.eid_value(type_id),
            point=point,
            system_id=self._system_id(element),
            size=self._size(element),
            length=quantize(length, quantum) if length else None,
            orientation=classify_direction(axis),
            axis=axis,
            label='{0}: {1}'.format(category_name, self._type_name(element, type_id)))


def collect_model_elements(doc, view, options):
    """Every taggable model element visible in ``view``, as records."""
    builder = RecordBuilder(doc, options)
    records = []
    collector = DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    for element in collector:
        if not builder.is_candidate(element):
            continue
        record = builder.build(element)
        if record is not None:
            records.append(record)
    return records
