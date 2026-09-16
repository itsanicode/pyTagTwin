# -*- coding: utf-8 -*-
"""Copy the tags and annotations of the active view into similar views."""

from pyrevit import forms, revit, script

from tagtwin import results
from tagtwin.revit import engine, ui

__title__ = 'Replicate\nAnnotations'
__author__ = 'Aniket Kesari'
__doc__ = ('Copies the tags, dimensions and annotations of the active view into '
           'other views showing the same thing - re-hosting every tag onto the '
           'matching element in the target view instead of leaving it pointing '
           'at the original.')

doc = revit.doc
source_view = revit.active_view
output = script.get_output()


def main():
    if doc is None or source_view is None:
        forms.alert('Open a project view first.', title='Tag Twin')
        return
    if not ui.can_annotate(source_view):
        forms.alert('Tag Twin works between drawing views - sheets, schedules '
                    'and legends have nothing to match.', title='Tag Twin')
        return

    options = ui.load_options()
    targets = ui.pick_target_views(doc, source_view)
    if not targets:
        return

    source = engine.build_source(doc, source_view, options)
    if not source.items:
        forms.alert('"{0}" has no annotation that Tag Twin can copy.'
                    .format(source.name), title='Tag Twin')
        return
    if not source.records:
        forms.alert('"{0}" shows no model element, so there is nothing to match '
                    'against.'.format(source.name), title='Tag Twin')
        return

    analyses = []
    with forms.ProgressBar(title='Matching views - {value} of {max_value}',
                           cancellable=True) as progress:
        for index, view in enumerate(targets, start=1):
            if progress.cancelled:
                return
            progress.update_progress(index, len(targets))
            analyses.append(engine.analyze(source, view, options))

    ui.print_analysis(output, source, analyses)
    usable = [a for a in analyses if a.verdict != 'poor']
    if not usable:
        forms.alert('None of the selected views matches "{0}" well enough to '
                    'copy anything.\n\nThe match report lists what was found. '
                    'Raising the tolerance in the settings often helps when the '
                    'second layout was modelled by hand.'.format(source.name),
                    title='Tag Twin')
        return

    if not ui.confirm(ui.run_prompt(source, analyses, usable)):
        return

    run_report = results.RunReport(source.name)
    for analysis in analyses:
        if analysis not in usable:
            report = results.ViewReport(analysis.view_id, analysis.name,
                                        analysis.solve_result)
            report.aborted = ('only {0:.0%} of the source elements matched'
                              .format(analysis.coverage))
            run_report.add(report)

    with revit.TransactionGroup('Tag Twin: replicate annotations', doc=doc):
        for analysis in usable:
            with revit.Transaction('Tag Twin: {0}'.format(analysis.name),
                                   doc=doc, swallow_errors=True):
                try:
                    run_report.add(engine.replicate(source, analysis, options))
                except Exception as error:
                    report = results.ViewReport(analysis.view_id, analysis.name,
                                                analysis.solve_result)
                    report.aborted = ui.short_error(error)
                    run_report.add(report)

    ui.print_run_report(output, run_report)
    ui.show_summary_alert(run_report)


main()
