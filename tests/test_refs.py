# -*- coding: utf-8 -*-
"""Re-pointing a Revit reference from an element onto its twin."""

from __future__ import division

import fake_revit

DB = fake_revit.install()

from tagtwin.revit import compat, refs   # noqa: E402  - needs the fake first

CASES = []


def case(func):
    CASES.append(func)
    return func


def _doc(*element_ids):
    return fake_revit.Document(element_ids)


ID_MAP = {346189: 500001, 149096: 500002}


@case
def test_whole_element_reference_is_repointed():
    doc = _doc(346189, 500001)
    reference = DB.Reference(representation='346189')
    remapped = refs.remap_reference(doc, reference, ID_MAP)
    assert remapped is not None
    assert remapped.ConvertToStableRepresentation(doc) == '500001'
    assert compat.eid_value(remapped.ElementId) == 500001


@case
def test_face_reference_keeps_its_geometry_part():
    """The tail addresses geometry inside the family - only the id changes."""
    doc = _doc(346189, 500001)
    reference = DB.Reference(representation='346189:0:SURFACE')
    remapped = refs.remap_reference(doc, reference, ID_MAP)
    assert remapped.ConvertToStableRepresentation(doc) == '500001:0:SURFACE'


@case
def test_instance_chain_only_swaps_the_instance():
    """The symbol geometry id is shared by both instances and must survive."""
    doc = _doc(149096, 500002)
    reference = DB.Reference(representation='149096:0:INSTANCE:149094:2:SURFACE')
    remapped = refs.remap_reference(doc, reference, ID_MAP)
    assert (remapped.ConvertToStableRepresentation(doc)
            == '500002:0:INSTANCE:149094:2:SURFACE')


@case
def test_unmatched_element_gives_nothing():
    doc = _doc(999, 500001)
    reference = DB.Reference(representation='999:0:SURFACE')
    assert refs.remap_reference(doc, reference, ID_MAP) is None


@case
def test_linked_references_are_refused():
    """A reference into a linked model cannot be re-pointed inside this file."""
    doc = _doc(346189, 500001)
    reference = DB.Reference(representation='346189:0:RVTLINK:12:0:SURFACE')
    assert refs.remap_reference(doc, reference, ID_MAP) is None
    assert refs.remap_reference(doc, reference, ID_MAP,
                                allow_element_fallback=True) is not None


@case
def test_fallback_is_only_offered_when_asked_for():
    """A tag may fall back to the whole element; a dimension may not."""
    doc = _doc(346189, 500001)
    reference = DB.Reference(
        representation='346189:9:{0}'.format(fake_revit.UNRESOLVABLE))
    assert refs.remap_reference(doc, reference, ID_MAP,
                                allow_element_fallback=False) is None
    fallback = refs.remap_reference(doc, reference, ID_MAP,
                                    allow_element_fallback=True)
    assert fallback is not None
    assert compat.eid_value(fallback.ElementId) == 500001


@case
def test_representation_that_disagrees_with_the_element_is_not_rewritten():
    """Never rewrite a representation whose leading id is not the one reported."""
    doc = _doc(346189, 500001)
    reference = DB.Reference(representation='346189:0:SURFACE')
    reference.ElementId = DB.ElementId(346189)
    reference._representation = '777:0:SURFACE'   # inconsistent - refuse it
    assert refs.remap_reference(doc, reference, ID_MAP) is None


@case
def test_remap_all_splits_mapped_from_unmapped():
    doc = _doc(346189, 149096, 500001, 500002)
    references = [DB.Reference(representation='346189'),
                  DB.Reference(representation='149096:0:SURFACE'),
                  DB.Reference(representation='4242')]
    mapped, unmapped = refs.remap_all(doc, references, ID_MAP)
    assert len(mapped) == 2
    assert unmapped == [4242]
    assert all(len(pair) == 2 for pair in mapped)


@case
def test_target_missing_from_document_is_reported_not_crashed():
    doc = _doc(346189)          # 500001 was deleted
    reference = DB.Reference(representation='346189:0:SURFACE')
    assert refs.remap_reference(doc, reference, ID_MAP) is None
    assert refs.remap_reference(doc, reference, ID_MAP,
                                allow_element_fallback=True) is None


@case
def test_eid_value_handles_both_api_generations():
    class Legacy(object):
        IntegerValue = 4242
    assert compat.eid_value(DB.ElementId(7)) == 7        # 2024+ .Value
    assert compat.eid_value(Legacy()) == 4242            # 2023 and earlier
    assert compat.eid_value(None) is None
