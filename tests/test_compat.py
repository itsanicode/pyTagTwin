# -*- coding: utf-8 -*-
"""Guard rails for the two engines pyRevit can run scripts on.

pyRevit's default engine is IronPython 2.7, so every file shipped in the
extension has to parse as Python 2 *and* Python 3. These tests can only be run
by a Python 3 interpreter, so they check the syntax that differs by scanning the
source rather than by importing it.
"""

from __future__ import division

import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)

#: the repo root is the extension bundle, so "what ships" is lib/ and the tab -
#: tests/ and tools/ are development files that never run inside Revit
SHIPPED = ('lib', 'Tag Twin.tab')

PY3_ONLY = (
    (re.compile(r'''(^|[^\w'"])[fF](['"])'''), 'f-string'),
    (re.compile(r'[^:=!<>]:=[^=]'), 'walrus operator'),
    (re.compile(r'^\s*(async|await)\s'), 'async/await'),
    (re.compile(r'^\s*nonlocal\s'), 'nonlocal'),
    (re.compile(r'^\s*def\s+\w+\([^)]*\)\s*->'), 'return annotation'),
    (re.compile(r'^\s*yield\s+from\s'), 'yield from'),
)

CASES = []


def case(func):
    CASES.append(func)
    return func


def shipped_sources():
    for top in SHIPPED:
        for root, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for name in sorted(files):
                if name.endswith('.py'):
                    yield os.path.join(root, name)


@case
def test_sources_are_python2_compatible():
    problems = []
    for path in shipped_sources():
        with open(path, 'rb') as handle:
            text = handle.read().decode('utf-8')
        for number, line in enumerate(text.splitlines(), start=1):
            code = line.split('#', 1)[0]
            for pattern, label in PY3_ONLY:
                if pattern.search(code):
                    problems.append('{0}:{1}: {2}'.format(
                        os.path.basename(path), number, label))
    assert not problems, 'Python 3 only syntax found:\n  ' + '\n  '.join(problems)


@case
def test_sources_compile():
    import ast
    for path in shipped_sources():
        with open(path, 'rb') as handle:
            source = handle.read().decode('utf-8')
        try:
            ast.parse(source, filename=path)
        except SyntaxError as error:
            raise AssertionError('{0}: {1}'.format(path, error))


@case
def test_true_division_is_imported_where_dividing():
    """``/`` truncates on IronPython 2.7 without the future import."""
    offenders = []
    for path in shipped_sources():
        with open(path, 'rb') as handle:
            text = handle.read().decode('utf-8')
        if 'from __future__ import division' in text:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            code = line.split('#', 1)[0]
            code = re.sub(r'''(['"]).*?\1''', '', code)
            if re.search(r'(?<![/*])/(?![/*=])', code):
                offenders.append('{0}:{1}'.format(os.path.basename(path), number))
    assert not offenders, ('division without "from __future__ import division":\n  '
                           + '\n  '.join(offenders))


@case
def test_no_tabs_in_sources():
    offenders = [os.path.basename(p) for p in shipped_sources()
                 if '\t' in open(p, 'rb').read().decode('utf-8')]
    assert not offenders, 'tab indentation in: {0}'.format(offenders)


@case
def test_repo_root_is_the_extension_bundle():
    """pyRevit clones this repo straight into <Extensions>/pyTagTwin.extension.

    That means the repo root has to look like the *inside* of an extension
    folder. A nested "*.extension" directory here would end up double-nested
    once installed, and the Extension Manager button would silently do nothing.
    """
    entries = os.listdir(ROOT)
    assert not [e for e in entries if e.endswith('.extension')], \
        'the repo root must be the bundle itself, not contain one'
    assert os.path.isdir(os.path.join(ROOT, 'lib', 'tagtwin')), 'lib/tagtwin missing'
    tabs = [e for e in entries if e.endswith('.tab')]
    assert tabs, 'no .tab folder at the repo root'
    assert os.path.isfile(os.path.join(ROOT, 'extension.json'))


@case
def test_every_button_is_complete():
    """pyRevit finds tools by folder suffix - the layout has to be exact."""
    tabs = [e for e in os.listdir(ROOT) if e.endswith('.tab')]
    buttons = []
    for tab in tabs:
        panels = [d for d in os.listdir(os.path.join(ROOT, tab))
                  if d.endswith('.panel')]
        assert panels, 'no .panel in {0}'.format(tab)
        for panel in panels:
            panel_path = os.path.join(ROOT, tab, panel)
            for entry in sorted(os.listdir(panel_path)):
                if not entry.endswith('.pushbutton'):
                    continue
                button = os.path.join(panel_path, entry)
                for required in ('script.py', 'icon.png', 'bundle.yaml'):
                    assert os.path.isfile(os.path.join(button, required)), \
                        '{0} has no {1}'.format(entry, required)
                buttons.append(entry)
    assert len(buttons) == 5, buttons


@case
def test_bundle_metadata_parses():
    """A bundle.yaml pyRevit cannot read silently drops the button's title."""
    try:
        import yaml
    except ImportError:
        return
    found = 0
    for top in SHIPPED:
        for root, dirs, files in os.walk(os.path.join(ROOT, top)):
            if 'bundle.yaml' not in files:
                continue
            path = os.path.join(root, 'bundle.yaml')
            with open(path, 'rb') as handle:
                data = yaml.safe_load(handle.read().decode('utf-8'))
            assert isinstance(data, dict), path
            assert data.get('title'), 'no title in {0}'.format(path)
            found += 1
    assert found >= 6, found


@case
def test_extension_metadata_parses():
    import json
    with open(os.path.join(ROOT, 'extension.json'), 'rb') as handle:
        data = json.loads(handle.read().decode('utf-8'))
    assert data.get('name') == 'pyTagTwin', data
    assert data.get('author')


@case
def test_button_scripts_only_use_shipped_imports():
    """Buttons may import pyrevit and tagtwin - nothing else needs installing."""
    allowed = ('pyrevit', 'tagtwin', 'Autodesk', 'System', '__future__')
    offenders = []
    for path in shipped_sources():
        if os.path.basename(path) != 'script.py':
            continue
        with open(path, 'rb') as handle:
            text = handle.read().decode('utf-8')
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith('import ') or stripped.startswith('from ')):
                continue
            module = stripped.split()[1].split('.')[0]
            if module not in allowed:
                offenders.append('{0}:{1}: {2}'.format(
                    os.path.basename(os.path.dirname(path)), number, module))
    assert not offenders, offenders
