import json
import tempfile
import unittest
from pathlib import Path

from leakguard.cli import main


class BaselineTests(unittest.TestCase):
    def test_baseline_create_and_scan_ignore_known_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "leak.py"
            baseline = root / "baseline.json"
            source.write_text(
                "def read():\n    f = open('data.txt')\n",
                encoding="utf-8",
            )

            self.assertEqual(
                main(["baseline", "create", str(root), "--output", str(baseline)]),
                0,
            )
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["findings"]), 1)
            self.assertEqual(main(["scan", str(root), "--baseline", str(baseline)]), 0)

            source.write_text(
                "def read():\n"
                "    f = open('data.txt')\n"
                "    g = open('other.txt')\n",
                encoding="utf-8",
            )
            self.assertEqual(main(["scan", str(root), "--baseline", str(baseline)]), 1)


if __name__ == "__main__":
    unittest.main()