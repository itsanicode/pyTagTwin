# -*- coding: utf-8 -*-
"""Run the Tag Twin test suite without any third-party test runner.

    python run_tests.py [-v]
"""

from __future__ import division, print_function

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, os.pardir, 'lib')
TOOLS = os.path.join(HERE, os.pardir, 'tools')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(LIB))
sys.path.insert(0, os.path.abspath(TOOLS))

import test_compat      # noqa: E402
import test_core        # noqa: E402
import test_icons       # noqa: E402
import test_declutter   # noqa: E402
import test_layout      # noqa: E402
import test_margin      # noqa: E402
import test_outlook     # noqa: E402
import test_package     # noqa: E402
import test_refs        # noqa: E402  - installs a fake Revit API

MODULES = (test_core, test_layout, test_margin, test_declutter, test_outlook,
           test_refs, test_icons, test_package, test_compat)


def main(argv):
    verbose = '-v' in argv or '--verbose' in argv
    passed = 0
    failures = []
    for module in MODULES:
        for func in module.CASES:
            name = '{0}.{1}'.format(module.__name__, func.__name__)
            try:
                func()
            except Exception:
                failures.append((name, traceback.format_exc()))
                print('FAIL  {0}'.format(name))
            else:
                passed += 1
                if verbose:
                    print('ok    {0}'.format(name))
    print('\n{0} passed, {1} failed'.format(passed, len(failures)))
    for name, trace in failures:
        print('\n=== {0} ===\n{1}'.format(name, trace))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
