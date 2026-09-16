# -*- coding: utf-8 -*-
"""Just enough of the Revit API to exercise the reference remapping off Revit.

Only the handful of classes ``tagtwin.revit.refs`` touches are faked, and they
behave the way the real ones do in the ways that matter here: stable
representations are strings that start with an element id, and parsing one that
names an element the document does not have throws.
"""

from __future__ import division

import sys
import types


#: a token the fake refuses to parse, standing in for geometry
#: Revit cannot resolve on the target element
UNRESOLVABLE = 'NOSUCHGEOMETRY'


class ElementId(object):
    def __init__(self, value):
        self.Value = int(value)

    def __eq__(self, other):
        return isinstance(other, ElementId) and other.Value == self.Value

    def __hash__(self):
        return hash(self.Value)

    def __repr__(self):
        return 'ElementId({0})'.format(self.Value)


class Element(object):
    def __init__(self, id_value, representation=None):
        self.Id = ElementId(id_value)
        self.representation = representation or str(id_value)


class Reference(object):
    """A reference built either from an element or from a representation."""

    def __init__(self, element=None, representation=None):
        if element is not None:
            self.ElementId = element.Id
            self._representation = str(element.Id.Value)
        else:
            self._representation = representation
            self.ElementId = ElementId(int(representation.split(':')[0]))

    def ConvertToStableRepresentation(self, doc):
        if self._representation is None:
            raise RuntimeError('reference has no stable representation')
        return self._representation

    @staticmethod
    def ParseFromStableRepresentation(doc, representation):
        head = representation.split(':')[0]
        if doc.GetElement(ElementId(int(head))) is None:
            raise RuntimeError('no element {0} in this document'.format(head))
        if UNRESOLVABLE in representation:
            # stands in for a geometry id the twin element does not have, which
            # is what Revit throws on when the two elements are not really alike
            raise RuntimeError('cannot resolve {0}'.format(representation))
        return Reference(representation=representation)

    def __repr__(self):
        return '<Reference {0}>'.format(self._representation)


class Document(object):
    def __init__(self, element_ids=()):
        self._elements = dict((int(i), Element(i)) for i in element_ids)

    def add(self, element_id, representation=None):
        self._elements[int(element_id)] = Element(element_id, representation)

    def GetElement(self, element_id):
        return self._elements.get(element_id.Value)


def install():
    """Put the fake ``Autodesk.Revit.DB`` on ``sys.modules`` and return it."""
    db = types.ModuleType('Autodesk.Revit.DB')
    db.ElementId = ElementId
    db.Element = Element
    db.Reference = Reference

    revit = types.ModuleType('Autodesk.Revit')
    revit.DB = db
    autodesk = types.ModuleType('Autodesk')
    autodesk.Revit = revit

    sys.modules['Autodesk'] = autodesk
    sys.modules['Autodesk.Revit'] = revit
    sys.modules['Autodesk.Revit.DB'] = db
    return db
