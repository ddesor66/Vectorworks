import hashlib
import json
from pathlib import Path
import unittest

from PD_ToolsPD.ddvw.core.network_license import entry_checksum_valid


ROOT = Path(__file__).resolve().parents[1]


class EntryChecksumTests(unittest.TestCase):
    def test_newline_variants_are_the_only_equivalent_entry_sources(self):
        source_lf = b"from package import run\nrun()\n"
        source_crlf = source_lf.replace(b"\n", b"\r\n")
        expected = hashlib.sha256(source_lf).hexdigest()

        self.assertTrue(entry_checksum_valid(source_lf, expected))
        self.assertTrue(entry_checksum_valid(source_crlf, expected))
        self.assertFalse(entry_checksum_valid(source_lf + b"print('changed')\n", expected))
        self.assertFalse(entry_checksum_valid(source_lf, "not-a-sha256"))

    def test_every_declared_entry_matches_its_checked_out_script(self):
        package = ROOT / "PD_ToolsPD"
        entries = json.loads((package / "entries.json").read_text(encoding="utf-8"))
        for entry_name, expected in entries.items():
            path = package / "entries" / (entry_name + ".py")
            if not path.is_file():
                continue
            with self.subTest(entry=entry_name):
                self.assertTrue(entry_checksum_valid(path.read_bytes(), expected))


if __name__ == "__main__":
    unittest.main()
