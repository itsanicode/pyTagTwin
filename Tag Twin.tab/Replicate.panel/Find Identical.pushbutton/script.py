# -*- coding: utf-8 -*-
"""Select every element in the active view identical to what is selected."""

from pyrevit import forms, revit, script

from tagtwin import signature as sig
from tagtwin.revit import compat, engine, ui

__title__ = 'Find\nIdentical'
__author__ = 'Aniket Kesari'
__doc__ = ('Select one or more elements, then run this to select every other '
           'element in the view that is the same thing - same type, system and '
           'size. This is the fingerprint Tag Twin matches views on, so it is '
           'also the way to see why two views did or did not pair up.')

LEVELS = (
    ('Exact - same type, system and size', sig.STRICT),
    ('Same type and system, any size', sig.MEDIUM),
    ('Same type, anything else', sig.LOOSE),
)

doc = revit.doc
active_view = revit.active_view
output = script.get_output()


def main():
    if doc is None or active_view is None:
        forms.alert('Open a project view first.', title='Tag Twin')
        return

    selection = revit.get_selection()
    if not selection:
        forms.alert('Select the element you want to find copies of, then run '
                    'this again.', title='Tag Twin')
        return

    labels = [label for label, _ in LEVELS]
    chosen = forms.CommandSwitchWindow.show(
        labels, message='How alike do the elements have to be?')
    if not chosen:
        return
    level = dict(LEVELS)[chosen]

    options = ui.load_options()
    element_ids = [compat.eid_value(eid) for eid in selection.element_ids]
    matches, missing = engine.find_identical_elements(doc, active_view,
                                                      element_ids, options, level)
    if not matches:
        forms.alert('Nothing in this view matches the selection.\n\n'
                    'Elements hidden in the view are not searched.',
                    title='Tag Twin')
        return

    selection.set_to([compat.to_eid(record.key) for record in matches])

    groups = {}
    for record in matches:
        groups.setdefault(record.label, []).append(record)
    output.print_md('## Identical elements in "{0}"'.format(active_view.Name))
    output.print_md('**{0} element(s)** match the {1} selected, at the '
                    '"{2}" level. They are now selected.'.format(
                        len(matches), len(element_ids), chosen.lower()))
    if missing:
        output.print_md('_{0} selected element(s) are not visible in this view '
                        'and were ignored._'.format(len(missing)))
    rows = []
    for label in sorted(groups):
        rows.append([label, len(groups[label]),
                     ' '.join(output.linkify(compat.to_eid(r.key))
                              for r in groups[label][:25])])
    output.print_table(rows, title='By type',
                       columns=['Element', 'Count', 'Ids'])


main()
