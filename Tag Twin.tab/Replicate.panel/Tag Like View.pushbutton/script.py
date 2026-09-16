# -*- coding: utf-8 -*-
"""Tag another view the way the active view is tagged."""

from pyrevit import forms, revit, script

from tagtwin import results
from tagtwin.revit import tagging, ui

__title__ = 'Tag Like\nView'
__author__ = 'Aniket Kesari'
__doc__ = ('Learns how the active view is tagged - which tag type each kind of '
           'element gets, and how far the tag sits from it - then tags and '
           'arranges other views the same way. Unlike Replicate Annotations, '
           'this needs no element-to-element match between the views, only the '
           'same kinds of element, so it works where the views are similar '
           'rather than identical.')

doc = revit.doc
source_view = revit.active_view
output = script.get_output()


def main():
    if doc is None or source_view is None:
        forms.alert('Open a project view first.', title='Tag Twin')
        return
    if not ui.can_annotate(source_view):
        forms.alert('Tag Twin works between drawing views.', title='Tag Twin')
        return

    options = ui.load_options()
    level = options.layout_level

    recipe, orphaned = tagging.learn_view(doc, source_view, options, level)
    if not recipe.sample_count:
        forms.alert('"{0}" has no tag to learn from.\n\nOpen the view that is '
                    'already tagged the way you want, then run this.'
                    .format(source_view.Name), title='Tag Twin')
        return

    targets = ui.pick_target_views(
        doc, source_view,
        title='Tag these views like "{0}"'.format(source_view.Name))
    if not targets:
        return

    if not ui.confirm(ui.tag_like_prompt(source_view, recipe, targets,
                                         orphaned, options)):
        return

    run_report = results.RunReport(source_view.Name)
    with revit.TransactionGroup('Tag Twin: tag like view', doc=doc):
        for view in targets:
            with revit.Transaction('Tag Twin: {0}'.format(view.Name),
                                   doc=doc, swallow_errors=True):
                try:
                    run_report.add(tagging.apply_recipe(
                        doc, source_view, view, recipe, options, level))
                except Exception as error:
                    report = results.ViewReport(None, view.Name)
                    report.aborted = ui.short_error(error)
                    run_report.add(report)

    ui.print_recipe(output, source_view, recipe, orphaned)
    ui.print_run_report(output, run_report)
    ui.show_summary_alert(run_report)


main()
