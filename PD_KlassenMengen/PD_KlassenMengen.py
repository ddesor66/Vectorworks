# -*- coding: utf-8 -*-
"""Thin entry point loaded by the Vectorworks plug-in commands."""

from __future__ import absolute_import

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from PD_KlassenMengen.app import guarded_main  # noqa: E402


guarded_main(globals().get("PD_START_MODE", "home"))

