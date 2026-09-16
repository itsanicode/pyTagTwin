# -*- coding: utf-8 -*-
"""Re-point a Revit ``Reference`` from one element onto its twin.

This is what makes the copy intelligent rather than mechanical. A tag or a
dimension does not store a point, it stores a *reference*: "the centreline of
element 346189", "face 2 of element 149094". Copying the annotation as-is would
leave it pointing at the original element - which is exactly what Revit's own
copy/paste does, and why the pasted tags go blank.

A reference serialises to a stable representation that begins with the element
id it belongs to::

    "346189"                              a whole element
    "346189:0:SURFACE"                    a face of a system family
    "346189:0:INSTANCE:346045:2:SURFACE"  a face inside a family instance

Swapping the leading id for the matched element's id and parsing the result
gives the same reference *on the twin*. The trailing part addresses geometry
inside the family, so it stays valid as long as both elements are the same
type - which is the premise of the whole tool.
"""

from __future__ import division

from Autodesk.Revit import DB

from tagtwin.revit import compat

#: stable representations naming these cannot be re-pointed inside this document
UNSUPPORTED_TOKENS = ('RVTLINK', 'LINKEDFILE')


def reference_element_id(reference):
    try:
        return compat.eid_value(reference.ElementId)
    except Exception:
        return None


def remap_reference(doc, reference, id_map, allow_element_fallback=False):
    """The equivalent of ``reference`` on the matched element, or ``None``.

    ``allow_element_fallback`` returns a plain whole-element reference when the
    detailed one cannot be rebuilt. That is fine for a tag, which only needs to
    know *which* element it labels, but not for a dimension, which measures to a
    specific face and would silently move if it fell back.
    """
    source_id = reference_element_id(reference)
    if source_id is None:
        return None
    target_id = id_map.get(source_id)
    if target_id is None:
        return None

    try:
        representation = reference.ConvertToStableRepresentation(doc)
    except Exception:
        representation = None

    if representation:
        tokens = representation.split(':')
        if not any(token in UNSUPPORTED_TOKENS for token in tokens):
            head = tokens[0]
            if head.lstrip('-').isdigit() and int(head) == source_id:
                tokens[0] = str(target_id)
                try:
                    remapped = DB.Reference.ParseFromStableRepresentation(
                        doc, ':'.join(tokens))
                    if remapped is not None:
                        return remapped
                except Exception:
                    pass

    if not allow_element_fallback:
        return None
    element = doc.GetElement(compat.to_eid(target_id))
    if element is None:
        return None
    try:
        return DB.Reference(element)
    except Exception:
        return None


def remap_all(doc, references, id_map, allow_element_fallback=False):
    """``([(source reference, target reference), ...], [unmapped ids])``."""
    mapped = []
    unmapped = []
    for reference in references:
        remapped = remap_reference(doc, reference, id_map,
                                   allow_element_fallback=allow_element_fallback)
        if remapped is None:
            unmapped.append(reference_element_id(reference))
        else:
            mapped.append((reference, remapped))
    return mapped, unmapped
