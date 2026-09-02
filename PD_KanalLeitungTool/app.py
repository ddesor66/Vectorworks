# -*- coding: utf-8 -*-
"""Dispatch the common entry without coupling the two persistent models."""
from __future__ import absolute_import

import vs

from . import ui


def run():
    try:
        choice = ui.choose_module()
        if choice == "kanal":
            from PD_KanalTool import app
            app.run()
        elif choice == "leitung":
            from PD_LeitungsTool import app
            app.run()
        elif choice == "mengen":
            from PD_KanalLeitungMengen import app
            app.run()
    except Exception as error:
        vs.AlrtDialog("PD Fachmodule: " + str(error))
