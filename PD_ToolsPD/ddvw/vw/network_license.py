"""Fail-closed Vectorworks adapter; checks live identity on every invocation."""
import hashlib
import json
from pathlib import Path

import vs

from ..core.network_license import MAX_LICENSE_BYTES, validate_document
from ..core.public_key import PUBLIC_E, PUBLIC_N

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
LICENSE_PATH = PACKAGE_ROOT / "PD_Netzwerklizenz.json"


def authorized():
    """No cached approval, auto-enrollment, machine ID, or network request."""
    try:
        license_id = vs.Prot_GetLicenseID()
        serial = vs.GetActiveSerialNumber()
    except Exception:
        vs.AlrtDialog("PD-Tools: Vectorworks-Lizenzkennung konnte nicht gelesen werden.\n"
                      "Keine Zeichnung wurde durch diesen Aufruf veraendert.")
        return False
    series = serial[:1].upper() if isinstance(serial, str) and serial else ""
    try:
        with LICENSE_PATH.open("rb") as stream:
            raw = stream.read(MAX_LICENSE_BYTES + 1)
        return validate_document(raw, license_id, series, PUBLIC_N, PUBLIC_E)
    except FileNotFoundError:
        reason = "Die gemeinsame PD-Netzwerkfreigabe fehlt."
    except (OSError, ValueError, UnicodeError, TypeError, RecursionError):
        reason = "Die PD-Netzwerkfreigabe ist ungueltig oder passt nicht zu dieser Netzwerklizenz."
    vs.AlrtDialog("PD-Tools gesperrt\n\n" + reason + "\n\n"
                  "Bitte die gueltige PD_Netzwerklizenz.json durch die Administration "
                  "bereitstellen lassen. Bestehende Zeichnungsobjekte bleiben unveraendert.")
    return False


def launch(entry_name):
    if not authorized():
        return False
    try:
        entries = json.loads((PACKAGE_ROOT / "entries.json").read_text(encoding="utf-8"))
        if not isinstance(entry_name, str) or entry_name not in entries:
            raise ValueError("Unknown PD entry point")
        if "/" in entry_name or "\\" in entry_name or ".." in entry_name:
            raise ValueError("Invalid PD entry point")
        source_path = PACKAGE_ROOT / "entries" / (entry_name + ".py")
        source = source_path.read_bytes()
        if hashlib.sha256(source).hexdigest() != entries[entry_name]:
            raise ValueError("PD entry point checksum mismatch")
    except (OSError, ValueError, TypeError):
        vs.AlrtDialog("PD-Tools: Der Programmeinstieg fehlt oder wurde veraendert.\n"
                      "Bitte das gepruefte PD-Netzwerkupdate erneut installieren.")
        return False
    scope = {"__name__": "__main__", "__file__": str(source_path)}
    exec(compile(source, str(source_path), "exec"), scope, scope)
    return True
