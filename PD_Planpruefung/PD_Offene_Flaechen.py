"""Thin native menu entry point."""
import os
import sys

PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)
from PD_Planpruefung.open_shapes import guarded_run  # noqa: E402

guarded_run()
