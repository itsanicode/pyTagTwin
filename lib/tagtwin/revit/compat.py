# -*- coding: utf-8 -*-
"""Thin shims over the Revit API calls that changed between releases.

Tag Twin supports Revit 2021 to 2027. The differences that matter:

* ``ElementId.IntegerValue`` was replaced by ``ElementId.Value`` in 2024.
* ``IndependentTag`` gained multiple references in 2022, which turned
  ``GetTaggedReference()`` into ``GetTaggedReferences()`` and gave the leader
  accessors a reference argument.
"""

from __future__ import division

from Autodesk.Revit import DB

from tagtwin import geom


# --------------------------------------------------------------------------
# ids and points
# --------------------------------------------------------------------------

def eid_value(element_id):
    """The integer behind an ``ElementId``, on any supported release."""
    if element_id is None:
        return None
    try:
        return element_id.Value           # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue    # Revit 2023 and earlier


def to_eid(value):
    return DB.ElementId(value)


def xyz_tuple(xyz):
    if xyz is None:
        return None
    return (xyz.X, xyz.Y, xyz.Z)


def to_xyz(point):
    return DB.XYZ(point[0], point[1], point[2])


def to_transform(alignment):
    """Turn an :class:`tagtwin.geom.Alignment` into a Revit ``Transform``."""
    transform = DB.Transform.Identity
    transform.BasisX = to_xyz(alignment.basis_x)
    transform.BasisY = to_xyz(alignment.basis_y)
    transform.BasisZ = to_xyz(alignment.basis_z)
    transform.Origin = to_xyz(alignment.offset)
    return transform


def view_axes(view):
    """``(right, up, direction)`` of a view, as plain tuples."""
    return (xyz_tuple(view.RightDirection),
            xyz_tuple(view.UpDirection),
            xyz_tuple(view.ViewDirection))


def views_are_parallel(first, second, tolerance=1e-3):
    try:
        a = xyz_tuple(first.ViewDirection)
        b = xyz_tuple(second.ViewDirection)
    except Exception:
        return True
    return abs(abs(geom.dot(a, b)) - 1.0) < tolerance


# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------

def builtin(name):
    """``BuiltInParameter``/``BuiltInCategory`` by name, or ``None``.

    Looking them up by name keeps a release that dropped one from breaking the
    import of this module.
    """
    value = getattr(DB.BuiltInParameter, name, None)
    if value is None:
        value = getattr(DB.BuiltInCategory, name, None)
    return value


def param_double(element, builtin_parameter):
    if builtin_parameter is None:
        return None
    try:
        parameter = element.get_Parameter(builtin_parameter)
    except Exception:
        return None
    if parameter is None or not parameter.HasValue:
        return None
    try:
        return parameter.AsDouble()
    except Exception:
        return None


def param_eid_value(element, builtin_parameter):
    if builtin_parameter is None:
        return None
    try:
        parameter = element.get_Parameter(builtin_parameter)
    except Exception:
        return None
    if parameter is None or not parameter.HasValue:
        return None
    try:
        return eid_value(parameter.AsElementId())
    except Exception:
        return None


# --------------------------------------------------------------------------
# tags
# --------------------------------------------------------------------------

def tagged_references(tag):
    """Every reference a tag points at, oldest and newest API alike."""
    try:
        return list(tag.GetTaggedReferences())        # Revit 2022+
    except AttributeError:
        pass
    try:
        reference = tag.GetTaggedReference()
        return [reference] if reference is not None else []
    except Exception:
        return []


def tagged_element_ids(tag):
    values = []
    try:
        for element_id in tag.GetTaggedLocalElementIds():   # Revit 2022+
            value = eid_value(element_id)
            if value is not None and value > 0:
                values.append(value)
        return values
    except AttributeError:
        pass
    try:
        value = eid_value(tag.TaggedLocalElementId)
        if value is not None and value > 0:
            values.append(value)
    except Exception:
        pass
    return values


def get_leader_elbow(tag, reference):
    try:
        return tag.GetLeaderElbow(reference)          # Revit 2022+
    except Exception:
        pass
    try:
        return tag.LeaderElbow
    except Exception:
        return None


def get_leader_end(tag, reference):
    try:
        return tag.GetLeaderEnd(reference)          # Revit 2022+
    except Exception:
        pass
    try:
        return tag.LeaderEnd
    except Exception:
        return None


def set_leader_elbow(tag, reference, point):
    try:
        tag.SetLeaderElbow(reference, point)          # Revit 2022+
        return True
    except (AttributeError, TypeError):
        pass
    try:
        tag.LeaderElbow = point
        return True
    except Exception:
        return False


def set_leader_end(tag, reference, point):
    try:
        tag.SetLeaderEnd(reference, point)            # Revit 2022+
        return True
    except (AttributeError, TypeError):
        pass
    try:
        tag.LeaderEnd = point
        return True
    except Exception:
        return False


def net_list(item_type, items):
    """A ``List<T>`` for the API calls that will not take a Python list."""
    try:
        from System.Collections.Generic import List
    except ImportError:
        return list(items)
    typed = List[item_type]()
    for item in items:
        typed.Add(item)
    return typed
