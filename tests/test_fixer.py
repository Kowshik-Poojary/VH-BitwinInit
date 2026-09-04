import tempfile
import unittest
from pathlib import Path

from leakguard.cli import main


class FixerTests(unittest.TestCase):
    def test_simple_leak_is_fixed_and_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "simple.py"
            path.write_text(
                "def read():\n"
                "    f = open('data.txt')\n"
                "    return f.read()\n",
                encoding="utf-8",
            )

            self.assertEqual(main([str(path), "--fix"]), 0)
            self.assertIn("with open('data.txt') as f:", path.read_text(encoding="utf-8"))

    def test_branching_leak_is_not_auto_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "branch.py"
            original = (
                "def read(flag):\n"
                "    f = open('data.txt')\n"
                "    if flag:\n"
                "        return\n"
                "    f.close()\n"
            )
            path.write_text(original, encoding="utf-8")

            self.assertEqual(main([str(path), "--fix"]), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()