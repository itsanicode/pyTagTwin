# -*- coding: utf-8 -*-
"""Build the downloadable Tag Twin package.

    python make_package.py

Writes ``dist/pyTagTwin.zip``: the installer scripts, the README, and a clean
``pyTagTwin.extension`` folder holding only what Revit actually loads.

The repo root *is* the extension bundle - that is what lets pyRevit's Extension
Manager clone this repository straight into ``pyTagTwin.extension`` - so the
package deliberately lists the parts that ship rather than copying the root
wholesale. ``tests/`` and ``tools/`` stay out of the download.

The zip is built **deterministically**: entries are added in sorted order with a
fixed timestamp, so rebuilding it from unchanged sources produces a
byte-identical file. That keeps CI from committing a new package on every push
just because the clock moved.
"""

from __future__ import division, print_function

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, os.pardir))
DIST = os.path.join(PROJECT, 'dist')
ARCHIVE = os.path.join(DIST, 'pyTagTwin.zip')
ROOT = 'pyTagTwin'
BUNDLE = 'pyTagTwin.extension'

#: fixed timestamp - the earliest a zip entry can carry
EPOCH = (1980, 1, 1, 0, 0, 0)

#: what Revit loads - also exactly what the installer copies out of a clone
EXTENSION_CONTENT = ('extension.json', 'lib', 'Tag Twin.tab')

#: (source path relative to the repo root, path inside the zip)
CONTENTS = (
    (('installer/Install Tag Twin.bat', 'Install Tag Twin.bat'),
     ('installer/Uninstall Tag Twin.bat', 'Uninstall Tag Twin.bat'),
     ('installer/tagtwin-install.ps1', 'tagtwin-install.ps1'),
     ('README.md', 'README.md'))
    + tuple((name, '{0}/{1}'.format(BUNDLE, name)) for name in EXTENSION_CONTENT)
)

SKIP_DIRS = ('__pycache__', '.git')
SKIP_SUFFIXES = ('.pyc', '.pyo')


def _files(source, prefix):
    """``[(absolute path, path inside the zip), ...]``, sorted."""
    if os.path.isfile(source):
        return [(source, prefix)]
    found = []
    for directory, subdirectories, names in os.walk(source):
        subdirectories[:] = sorted(d for d in subdirectories if d not in SKIP_DIRS)
        for name in sorted(names):
            if name.endswith(SKIP_SUFFIXES):
                continue
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, source).replace(os.sep, '/')
            found.append((path, '{0}/{1}'.format(prefix, relative)))
    return found


def build(archive=ARCHIVE):
    entries = []
    for source, prefix in CONTENTS:
        path = os.path.join(PROJECT, source)
        if not os.path.exists(path):
            raise SystemExit('missing from the package: {0}'.format(source))
        entries.extend(_files(path, prefix))
    entries.sort(key=lambda entry: entry[1])

    if not os.path.isdir(os.path.dirname(archive)):
        os.makedirs(os.path.dirname(archive))
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for path, name in entries:
            info = zipfile.ZipInfo('{0}/{1}'.format(ROOT, name), date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 0          # say "made on MS-DOS", not the build OS
            with open(path, 'rb') as handle:
                package.writestr(info, handle.read())
    return archive, entries


def main():
    archive, entries = build()
    print('{0}  ({1} files, {2:.1f} KB)'.format(
        os.path.relpath(archive, PROJECT), len(entries),
        os.path.getsize(archive) / 1024.0))
    for _, name in entries:
        print('   {0}/{1}'.format(ROOT, name))


if __name__ == '__main__':
    sys.exit(main())
