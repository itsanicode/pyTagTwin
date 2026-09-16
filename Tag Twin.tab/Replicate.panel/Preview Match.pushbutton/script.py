# -*- coding: utf-8 -*-
"""Report how well other views match the active one. Changes nothing."""

from pyrevit import forms, revit, script

from tagtwin.revit import engine, ui

__title__ = 'Preview\nMatch'
__author__ = 'Aniket Kesari'
__doc__ = ('Dry run: works out how the active view lines up with the views you '
           'pick and reports what would be copied - which elements pair up, '
           'which have no twin, and which annotations would be skipped. '
           'Nothing in the model is changed.')

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
    targets = ui.pick_target_views(
        doc, source_view,
        title='Check "{0}" against...'.format(source_view.Name))
    if not targets:
        return

    source = engine.build_source(doc, source_view, options)
    analyses = []
    with forms.ProgressBar(title='Matching views - {value} of {max_value}',
                           cancellable=True) as progress:
        for index, view in enumerate(targets, start=1):
            if progress.cancelled:
                return
            progress.update_progress(index, len(targets))
            analyses.append(engine.analyze(source, view, options))

    ui.print_analysis(output, source, analyses)
    for analysis in analyses:
        output.print_md('### {0}'.format(analysis.name))
        output.print_md('- Transform: {0}'.format(analysis.describe_alignment()))
        output.print_md('- Confidence: {0:.0%} ({1})'.format(
            analysis.confidence, analysis.verdict))
        output.print_md('- **Would copy: {0}**'.format(
            analysis.outlook.summary() if analysis.outlook else 'nothing'))
        ui.print_match_detail(output, analysis, source)
    output.print_md('---')
    output.print_md('_Nothing was changed. Use **Replicate Annotations** to '
                    'copy the annotations across._')


main()
