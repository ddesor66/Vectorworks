# -*- coding: utf-8 -*-
import os
import vs
p = os.path.join(str(vs.GetFolderPath(-2) or ''), 'PD_Planpruefung', 'PD_Ueberlagernde_Linien.py')
if not os.path.isfile(p):
    vs.AlrtDialog('PD Planpruefung: Programmdatei fehlt.')
else:
    with open(p, 'r', encoding='utf-8-sig') as f:
        source = f.read()
    scope = {'__file__': p, '__name__': '__main__'}
    exec(compile(source, p, 'exec'), scope, scope)
