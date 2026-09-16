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
    ('tag_untagged_elements', 'Tag Like View: tag elements that have no tag yet'),
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


def nothing_to_place_message(source, analyses):
    """Say *why* a run would create nothing, not just that it would.

    "These views do not match well enough" is useless on its own - the useful
    part is which of the three things went wrong.
    """
    if not source.items:
        return ('"{0}" has no annotation that Tag Twin can copy.'
                .format(source.name))

    lines = ['Nothing can be copied from "{0}" into the selected view(s).'
             .format(source.name), '']
    for analysis in analyses:
        outlook = analysis.outlook
        if outlook is None:
            lines.append('  {0} - could not be analysed'.format(analysis.name))
            continue
        lines.append('  {0} - {1} of {2} elements matched, {3} of {4} tagged '
                     'elements'.format(analysis.name, analysis.matched,
                                       analysis.solve_result.match_result.source_count,
                                       outlook.hosted_matched, outlook.hosted_total))
    lines.append('')

    hosted = max([a.outlook.hosted_total for a in analyses if a.outlook] or [0])
    matched_any = any(a.outlook.hosted_matched for a in analyses if a.outlook)
    if not hosted:
        lines.append('Every annotation in the source view is attached to an '
                     'element, but none of those elements could be read. Run '
                     'Preview Match for the detail.')
    elif not matched_any:
        lines.append('None of the tagged elements has a twin in those views. '
                     'The usual causes, in order:')
        lines.append('')
        lines.append('  1. The tagged elements are not visible in the target '
                     'view - they have to be there for a tag to attach to.')
        lines.append('  2. The second layout was modelled by hand rather than '
                     'copied, so nothing lands inside the tolerance. Raise the '
                     'matching tolerance in Settings.')
        lines.append('  3. The two views really are showing different things.')
    else:
        lines.append('Some elements matched, but none of them is one that '
                     'carries an annotation.')
    lines.append('')
    lines.append('Preview Match lists every element that did and did not pair '
                 'up, with clickable ids.')
    return '\n'.join(lines)


def run_prompt(source, analyses, usable):
    """The last thing the user reads before anything is written to the model."""
    total = sum(a.placeable for a in usable)
    lines = ['About to copy {0} annotation(s) from "{1}" into {2} view(s):'
             .format(total, source.name, len(usable)), '']
    for analysis in analyses:
        if analysis in usable:
            lines.append('  {0} - {1}'.format(analysis.name,
                                              analysis.outlook.summary()))
        else:
            lines.append('  {0} - nothing to place, skipped'.format(analysis.name))
    partial = [a for a in usable if a.outlook.blocked]
    if partial:
        lines.append('')
        lines.append('{0} view(s) will skip some annotations because the '
                     'element they point at has no twin. Every one is listed '
                     'in the report with its reason.'.format(len(partial)))
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


def tag_like_prompt(source_view, recipe, targets, orphaned, options):
    """What Tag Like View is about to do, before it touches the model."""
    lines = ['Learned the tag layout of "{0}": {1}.'.format(
        source_view.Name, recipe.describe()), '']
    if orphaned:
        lines.append('{0} tag(s) were ignored - the element they label is not '
                     'in this view.'.format(orphaned))
        lines.append('')
    lines.append('About to apply it to {0} view(s):'.format(len(targets)))
    for view in targets:
        lines.append('  {0}'.format(view.Name))
    lines.append('')
    if options.tag_untagged_elements:
        lines.append('Elements with no tag yet will be tagged, using the same '
                     'tag type the reference view uses for that category. '
                     'Existing tags are moved, not duplicated.')
    else:
        lines.append('Only tags that already exist will be moved - switch on '
                     '"tag elements that have no tag yet" in the settings to '
                     'place missing ones too.')
    lines.append('')
    lines.append('This can be undone in one step. Carry on?')
    return '\n'.join(lines)


def print_recipe(output, source_view, recipe, orphaned):
    """What was learned, so a surprising result can be explained."""
    output.print_md('## Tag Twin - layout learned from "{0}"'.format(
        source_view.Name))
    output.print_md('**{0}**'.format(recipe.describe()))
    if orphaned:
        output.print_md('_{0} tag(s) ignored: the element they label is not a '
                        'model element of this view._'.format(orphaned))
    rows = []
    for category in sorted(recipe.by_category):
        placement = recipe.by_category[category]
        type_id = recipe.tag_type_for(category)
        positions = sum(1 for signature in recipe.by_signature
                        if recipe.by_signature[signature]
                        and _category_of(recipe, signature) == category)
        rows.append([
            category,
            output.linkify(compat.to_eid(type_id)) if type_id else '-',
            positions or 1,
            '{0:+.2f}, {1:+.2f} ft'.format(placement.offset[0],
                                           placement.offset[1]),
        ])
    if rows:
        output.print_table(
            rows, title='Tag types and typical offsets',
            columns=['Element category', 'Tag type', 'Distinct kinds',
                     'Average offset (right, up)'])
    output.print_md('_Offsets are measured along the view\'s own right and up '
                    'axes, so they land the same way on the sheet whichever '
                    'direction the target view looks._')


def _category_of(recipe, signature):
    """The category a signature belongs to - it is the first element of it."""
    try:
        return signature[0]
    except Exception:
        return None


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
        outlook = analysis.outlook
        rows.append([
            view_link(output, analysis.view_id, analysis.name),
            '{0} / {1}'.format(outlook.placeable, outlook.total) if outlook else '-',
            '{0:.0%}'.format(outlook.host_coverage) if outlook else '-',
            '{0} / {1}'.format(analysis.matched,
                               analysis.solve_result.match_result.source_count),
            '{0:.0%}'.format(analysis.coverage),
            analysis.verdict,
            analysis.describe_alignment(),
        ])
    output.print_table(
        rows, title='What would be copied',
        columns=['Target view', 'Annotations', 'Tagged elements',
                 'All elements', 'Coverage', 'Match', 'Transform'])
    output.print_md(
        '_**Annotations** is what decides whether a run does anything: how many '
        'of the source annotations have a matched element to hang on. '
        '**Tagged elements** is the share of the elements that carry an '
        'annotation which found a twin. **Coverage** counts every model element '
        'in the view, tagged or not - a riser that is mostly bare pipework reads '
        'low here and still copies across perfectly._')


def print_match_detail(output, analysis, source=None, limit=40):
    """Per-element detail for the preview tool.

    When ``source`` is given, the elements that actually carry an annotation are
    called out first. Those are the only unmatched elements that cost you
    anything - the rest of a riser is bare pipework nobody tags.
    """
    result = analysis.solve_result.match_result
    if source is not None:
        hosts = set()
        for item in source.items:
            hosts.update(item.host_ids or ())
        stranded = [r for r in result.unmatched_source if r.key in hosts]
        if stranded:
            output.print_md(
                '**{0} element(s) carrying an annotation have no twin here.** '
                'Their annotations are what would be skipped - check they are '
                'visible in the target view:'.format(len(stranded)))
            output.print_table(
                [[output.linkify(compat.to_eid(r.key)), r.label]
                 for r in stranded[:limit]],
                columns=['Element', 'Type'])
        elif hosts:
            output.print_md('**Every annotated element found a twin.**')
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
        output.print_md('{0} source element(s) have no twin. Most of these will '
                        'be untagged pipework, which costs nothing:'.format(
                            len(result.unmatched_source)))
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
