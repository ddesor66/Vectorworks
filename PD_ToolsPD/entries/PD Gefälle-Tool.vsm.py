# -*- coding: utf-8 -*-
import os
import vs
p = os.path.join(str(vs.GetFolderPath(-2) or ''), 'PD_GefaelleTool', 'PD_GefaelleTool.py')
if not os.path.isfile(p):
    found, candidate = vs.FindFileInPluginFolder('PD_GefaelleTool.py')
    p = str(candidate or '') if found else ''
if not p or not os.path.isfile(p):
    vs.AlrtDialog('PD Gefaelle-Tool: Die installierte Anwendung wurde nicht gefunden.')
else:
    with open(p, 'r', encoding='utf-8-sig') as stream:
        source = stream.read()
    scope = {'__file__': p, '__name__': '__main__'}
    exec(compile(source, p, 'exec'), scope, scope)
