# -*- coding: utf-8 -*-
"""The committed download package must match the sources it is built from.

``make_package.py`` builds the zip deterministically, so a plain byte
comparison is enough - and it fails loudly when someone changes the extension
and forgets to rebuild the download.
"""

from __future__ import division

import os
import shutil
import tempfile
import zipfile

import make_package

CASES = []


def case(func):
    CASES.append(func)
    return func


@case
def test_package_is_up_to_date():
    assert os.path.isfile(make_package.ARCHIVE), \
        'dist/pyTagTwin.zip is missing - run "python tools/make_package.py"'
    scratch = tempfile.mkdtemp()
    try:
        rebuilt = os.path.join(scratch, 'pyTagTwin.zip')
        make_package.build(rebuilt)
        with open(rebuilt, 'rb') as handle:
            expected = handle.read()
        with open(make_package.ARCHIVE, 'rb') as handle:
            actual = handle.read()
    finally:
        shutil.rmtree(scratch)
    assert actual == expected, (
        'dist/pyTagTwin.zip is stale - the extension changed since it was built. '
        'Run "python tools/make_package.py" and commit the result.')


@case
def test_package_builds_deterministically():
    """Two builds of the same sources must be byte-identical, or CI churns."""
    scratch = tempfile.mkdtemp()
    try:
        first = os.path.join(scratch, 'one.zip')
        second = os.path.join(scratch, 'two.zip')
        make_package.build(first)
        make_package.build(second)
        assert open(first, 'rb').read() == open(second, 'rb').read()
    finally:
        shutil.rmtree(scratch)


@case
def test_package_has_what_the_installer_needs():
    with zipfile.ZipFile(make_package.ARCHIVE) as package:
        names = package.namelist()
        assert package.testzip() is None, 'the package is corrupt'
    bundle = 'pyTagTwin/pyTagTwin.extension'
    required = (
        'pyTagTwin/Install Tag Twin.bat',
        'pyTagTwin/Uninstall Tag Twin.bat',
        'pyTagTwin/tagtwin-install.ps1',
        'pyTagTwin/README.md',
        bundle + '/extension.json',
        bundle + '/lib/tagtwin/__init__.py',
        bundle + '/lib/tagtwin/revit/engine.py',
    )
    for name in required:
        assert name in names, 'missing from the package: {0}'.format(name)
    # the installer checks for lib\tagtwin to decide it found the extension
    assert any(n.startswith(bundle + '/lib/tagtwin/') for n in names)
    # all four buttons, with their icons
    buttons = set(n.split('/')[4] for n in names
                  if '.pushbutton/' in n and n.count('/') > 4)
    assert len(buttons) == 4, buttons
    for button in buttons:
        for part in ('script.py', 'icon.png', 'bundle.yaml'):
            path = bundle + '/Tag Twin.tab/Replicate.panel/{0}/{1}'
            assert path.format(button, part) in names, (button, part)


@case
def test_package_ships_no_build_leftovers():
    with zipfile.ZipFile(make_package.ARCHIVE) as package:
        names = package.namelist()
    junk = [n for n in names
            if '__pycache__' in n or n.endswith(('.pyc', '.pyo'))]
    assert not junk, junk
    # tests and tools are development files - they do not belong in a download
    assert not [n for n in names if '/tests/' in n or '/tools/' in n], names
