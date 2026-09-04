import unittest
from pathlib import Path

from leakguard.scanner import scan_path


class BenchmarkTests(unittest.TestCase):
    def test_seeded_cases_match_expected_results(self):
        root = Path(__file__).parents[1] / "benchmarks"
        expected_leaks = {
            "01_obvious_leak.py",
            "03_early_return.py",
            "05_branch_leak.py",
            "07_exception_return.py",
        }
        for path in sorted(root.glob("*.py")):
            with self.subTest(case=path.name):
                result = scan_path(path)
                has_leak = bool(result.findings)
                self.assertEqual(has_leak, path.name in expected_leaks)


if __name__ == "__main__":
    unittest.main()
