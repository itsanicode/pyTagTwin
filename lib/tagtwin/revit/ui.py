# -*- coding: utf-8 -*-
"""pyRevit forms, settings storage and the run report.

Kept to pyRevit's own form classes rather than custom XAML: they behave the
same on the IronPython and CPython engines, and they are what a pyRevit user
already knows.
"""

from __future__ import division

from pyrevit import forms, script

from tagtwin import results
from tagtwin.options import MatchOptions
from tagtwin.revit import compat

CONFIG_SECTION = 'tagtwin'

#: the switches worth showing, in the order they are asked about
TOGGLES = (
    ('allow_mirror', 'Match mirrored (handed) layouts'),
    ('allow_rotation', 'Match rotated layouts'),
    ('use_relaxed_levels', 'Fall back to looser matching when sizes differ'),
    ('rehost_to_matched_point', 'Keep tags at the same offset from their element'),
    ('adapt_to_view_scale', 'Adjust offsets and text width for the view scale'),
    ('skip_existing', 'Skip annotations that are already there'),
    ('lock_3d_views', 'Lock target 3D views automatically (needed for tags)'),
    ('copy_tags', 'Copy tags'),
    ('copy_dimensions', 'Copy dimensions'),
    ('copy_spot_dimensions', 'Copy spot dimensions'),
    ('copy_text', 'Copy text notes'),
    ('copy_detail_lines', 'Copy detail lines'),
    ('copy_regions', 'Copy filled regions and clouds'),
    ('copy_symbols', 'Copy annotation symbols'),
)


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

def load_options():
    """Options from the user's pyRevit config, falling back to the defaults."""
    config = script.get_config(CONFIG_SECTION)
    stored = {}
    for name in MatchOptions.field_names():
        try:
            value = config.get_option(name, None)
        except Exception:
            value = None
        if value is not None:
            stored[name] = value
    try:
        return MatchOptions.from_dict(stored)
    except Exception:
        return MatchOptions()


def save_options(options):
    config = script.get_config(CONFIG_SECTION)
    for name, value in options.to_dict().items():
        setattr(config, name, value)
    script.save_config()


def edit_options(options):
    """Let the user edit the settings. Returns the new options, or ``None``."""
    items = [forms.TemplateListItem(label, checked=bool(getattr(options, name)))
             for name, label in TOGGLES]
    chosen = forms.SelectFromList.show(
        items, title='Tag Twin settings', button_name='Save settings',
        multiselect=True, width=520, height=560)
    if chosen is None:          # closed without saving - an empty list is a save
        return None
    enabled = set(str(entry) for entry in unwrap_all(chosen))
    for name, label in TOGGLES:
        setattr(options, name, label in enabled)

    answer = forms.ask_for_string(
        default=str(options.position_tolerance),
        prompt=('How far apart may two elements be and still count as the same '
                'element?\nIn feet - 0.02 is about 6 mm. Raise it if the second '
                'suite was modelled by hand.'),
        title='Matching tolerance')
    if answer:
        try:
            tolerance = float(answer)
            if tolerance > 0:
                options.position_tolerance = tolerance
        except ValueError:
            forms.alert('"{0}" is not a number - the tolerance is unchanged.'
                        .format(answer))

    mode = forms.CommandSwitchWindow.show(
        ['auto', 'model', 'view'],
        message='How should annotation offsets be carried across?\n'
                'auto: model space for parallel views, view space otherwise')
    if mode:
        options.offset_mode = mode
    return options


# --------------------------------------------------------------------------
# pickers
# --------------------------------------------------------------------------

class ViewItem(forms.TemplateListItem):
    """A view in a pyRevit list, shown as "Floor Plan: Level 1"."""

    @property
    def name(self):
        try:
            return '{0}: {1}'.format(self.item.ViewType, self.item.Name)
        except Exception:
            return str(self.item)


def unwrap_all(selection):
    if not selection:
        return []
    out = []
    for entry in selection:
        out.append(entry.unwrap() if hasattr(entry, 'unwrap') else entry)
    return out


def pick_target_views(doc, source_view, title=None):
    """Ask which views to copy into. Returns a (possibly empty) list of views."""
    from tagtwin.revit import engine
    same_type, others = engine.candidate_target_views(doc, source_view)
    if not same_type and not others:
        forms.alert('This model has no other view to copy into.', title='Tag Twin')
        return []
    groups = {}
    if same_type:
        groups['Same type as "{0}"'.format(source_view.Name)] = \
            [ViewItem(v) for v in same_type]
    if others:
        groups['All other views'] = [ViewItem(v) for v in others]
    selection = forms.SelectFromList.show(
        groups,
        title=title or 'Copy the annotations of "{0}" into...'.format(source_view.Name),
        button_name='Use these views', multiselect=True, width=620, height=640)
    return unwrap_all(selection)


def can_annotate(view):
    """Whether a view is the kind that holds model elements and annotations."""
    from Autodesk.Revit import DB
    try:
        if view.IsTemplate:
            return False
        if isinstance(view, (DB.ViewSheet, DB.ViewSchedule)):
            return False
        return view.ViewType not in (DB.ViewType.Legend, DB.ViewType.DrawingSheet,
                                     DB.ViewType.Schedule, DB.ViewType.ProjectBrowser,
                                     DB.ViewType.SystemBrowser, DB.ViewType.Internal,
                                     DB.ViewType.Undefined)
    except Exception:
        return False


def short_error(error):
    text = getattr(error, 'Message', None) or str(error)
    return ' '.join(str(text).split())[:300]


def run_prompt(source, analyses, usable):
    """The last thing the user reads before anything is written to the model."""
    lines = ['About to copy {0} annotation(s) from "{1}" into {2} view(s):'
             .format(source.annotation_count, source.name, len(usable)), '']
    for analysis in analyses:
        if analysis in usable:
            lines.append('  {0} - {1:.0%} of elements matched ({2})'.format(
                analysis.name, analysis.coverage, analysis.verdict))
        else:
            lines.append('  {0} - skipped, too little matched ({1:.0%})'.format(
                analysis.name, analysis.coverage))
    weak = [a for a in usable if a.verdict == 'partial']
    if weak:
        lines.append('')
        lines.append('{0} view(s) matched only partially. Annotations on '
                     'unmatched elements will be skipped and listed in the '
                     'report.'.format(len(weak)))
    lines.append('')
    lines.append('This can be undone in one step. Carry on?')
    return '\n'.join(lines)


def confirm(message, title='Tag Twin'):
    return forms.alert(message, title=title, yes=True, no=True)


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def view_link(output, view_id, name):
    try:
        return output.linkify(compat.to_eid(view_id), name)
    except Exception:
        return name


def print_analysis(output, source, analyses):
    """The dry-run table: how well each target view lines up with the source."""
    output.print_md('## Tag Twin - match report')
    output.print_md('**Source view:** {0} - {1} model elements, '
                    '{2} annotations'.format(source.name, len(source.records),
                                             source.annotation_count))
    if source.items:
        kinds = ', '.join('{0} x {1}'.format(count, kind)
                          for kind, count in source.kind_counts())
        output.print_md('**Annotations found:** {0}'.format(kinds))
    if source.unsupported:
        output.print_md('**Not supported:** {0} annotation(s) Tag Twin cannot '
                        'rebuild'.format(len(source.unsupported)))

    rows = []
    for analysis in analyses:
        rows.append([
            view_link(output, analysis.view_id, analysis.name),
            len(analysis.records),
            '{0} / {1}'.format(analysis.matched,
                               analysis.solve_result.match_result.source_count),
            '{0:.0%}'.format(analysis.coverage),
            '{0:.0%}'.format(analysis.confidence),
            analysis.verdict,
            analysis.describe_alignment(),
        ])
    output.print_table(
        rows, title='How the views line up',
        columns=['Target view', 'Elements', 'Matched', 'Coverage',
                 'Confidence', 'Verdict', 'Transform'])


def print_match_detail(output, analysis, limit=40):
    """Per-element detail for the preview tool."""
    result = analysis.solve_result.match_result
    relaxed = [m for m in result.matches if not m.is_exact]
    ambiguous = [m for m in result.matches if m.ambiguous]
    if relaxed:
        output.print_md('**{0} element(s) matched on a looser signature** - '
                        'check these before relying on the run:'.format(len(relaxed)))
        rows = [[output.linkify(compat.to_eid(m.source.key)),
                 output.linkify(compat.to_eid(m.target.key)),
                 m.source.label, '{0:.4f} ft'.format(m.distance)]
                for m in relaxed[:limit]]
        output.print_table(rows, columns=['Source', 'Target', 'Element', 'Distance'])
    if ambiguous:
        output.print_md('**{0} element(s) had more than one equally good '
                        'candidate** - the nearest was used:'.format(len(ambiguous)))
    if result.unmatched_source:
        output.print_md('**{0} source element(s) have no twin** - annotations on '
                        'them will be skipped:'.format(len(result.unmatched_source)))
        rows = [[output.linkify(compat.to_eid(r.key)), r.label]
                for r in result.unmatched_source[:limit]]
        output.print_table(rows, columns=['Element', 'Type'])
        if len(result.unmatched_source) > limit:
            output.print_md('_...and {0} more._'.format(
                len(result.unmatched_source) - limit))


def print_run_report(output, run_report):
    output.print_md('## Tag Twin - run report')
    output.print_md('**{0}**'.format(run_report.headline()))
    for report in run_report.views:
        output.print_md('### {0}'.format(report.view_name))
        for note in report.notes:
            output.print_md('- {0}'.format(note))
        if report.aborted:
            output.print_md('**Nothing was created: {0}.**'.format(report.aborted))
            continue
        rows = report.by_kind()
        if rows:
            output.print_table(rows, columns=['Annotation', 'Created',
                                              'Skipped', 'Failed'])
        reasons = report.reasons()
        if reasons:
            output.print_table(
                [[status, message, count] for status, message, count in reasons],
                title='What did not get created',
                columns=['Status', 'Reason', 'Count'])


def show_summary_alert(run_report):
    lines = [run_report.headline(), '']
    for report in run_report.views:
        lines.append(report.headline())
    lines.append('')
    lines.append('The report window lists every annotation and why any were '
                 'skipped.')
    forms.alert('\n'.join(lines), title='Tag Twin')
