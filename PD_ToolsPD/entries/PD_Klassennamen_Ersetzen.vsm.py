import os,vs
f='KlassennamenErsetzen.py'
p=os.path.join(str(vs.GetFolderPath(-2) or ''),'KlassennamenErsetzen',f)
if not os.path.isfile(p):
 b,p=vs.FindFileInPluginFolder(f)
 p=str(p or '') if b else ''
 if os.path.isdir(p): p=os.path.join(p,f)
if not os.path.isfile(p): vs.AlrtDialog('Programmdatei fehlt: '+f)
else:
 s={'__file__':p,'__name__':'__main__'}
 with open(p,encoding='utf-8-sig') as h: exec(compile(h.read(),p,'exec'),s,s)
