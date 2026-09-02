# -*- coding: utf-8 -*-
from importlib import reload

import PD_GelaendeBaugruben as package
from PD_GelaendeBaugruben import app, core, reporting, ui, vw_adapter

# Vectorworks keeps its embedded Python interpreter alive for the whole
# application session.  Reload the terrain package on every menu invocation so
# a verified plugin update is active immediately without a Vectorworks restart.
reload(package)
reload(core)
reload(reporting)
reload(ui)
reload(vw_adapter)
reload(app)

app.run()
