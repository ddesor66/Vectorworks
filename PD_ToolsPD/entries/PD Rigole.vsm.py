# -*- coding: utf-8 -*-
import vs
if not vs.SetToolByName('Rigolen'):
    vs.AlrtDialog('PD Rigole: Das Werkzeug Rigolen wurde nicht gefunden. Bitte die Tools-PD-Installation prüfen.')
