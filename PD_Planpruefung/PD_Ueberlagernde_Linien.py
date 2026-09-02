# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from PD_Planpruefung.duplicates import run

run()

