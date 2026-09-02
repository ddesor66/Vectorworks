"""Common entry for all maintained PD menu commands and tools."""


def launch(entry_name):
    from .ddvw.vw.network_license import launch as run
    return run(entry_name)


def authorized():
    from .ddvw.vw.network_license import authorized as check
    return check()
