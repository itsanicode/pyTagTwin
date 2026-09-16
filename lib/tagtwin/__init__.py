# -*- coding: utf-8 -*-
"""Tag Twin - replicate tags and annotations between similar views.

The package is split in two halves:

``tagtwin.geom``, ``tagtwin.signature``, ``tagtwin.spatial``, ``tagtwin.align``
and ``tagtwin.matching`` are **pure Python** (2.7 and 3.x) and never import the
Revit API, so the matching engine can be unit tested outside Revit.

``tagtwin.revit`` holds everything that touches the Revit API: collecting
elements from a view, reading the annotations of a view and re-creating them in
another one.
"""

__version__ = '1.0.0'
__author__ = 'Aniket Kesari'
