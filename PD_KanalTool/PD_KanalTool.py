# -*- coding: utf-8 -*-
"""Vectorworks entry point for the independent channel tool."""

from __future__ import absolute_import

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from PD_KanalTool.app import run  # noqa: E402


run()
