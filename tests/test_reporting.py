import json
import unittest

from leakguard.detector import Finding
from leakguard.reporting import json_report, sarif_report


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.finding = Finding(
            filename="examples/leak.py",
            scope="test",
            resource_type="File",
            variable="f",
            opened_line=2,
            closed_line=None,
            reason="Resource remains open on at least one reachable path.",
        )

    def test_json_report_contains_classification_and_location(self):
        report = json.loads(json_report([self.finding]))

        self.assertEqual(report["version"], 1)
        self.assertEqual(report["findings"][0]["classification"], "DEFINITE_LEAK")
        self.assertEqual(report["findings"][0]["opened_line"], 2)

    def test_sarif_report_contains_result_location(self):
        report = json.loads(sarif_report([self.finding]))

        self.assertEqual(report["version"], "2.1.0")
        result = report["runs"][0]["results"][0]
        self.assertEqual(result["ruleId"], "LEAKGUARD001")
        self.assertEqual(
            result["locations"][0]["physicalLocation"]["region"]["startLine"],
            2,
        )


if __name__ == "__main__":
    unittest.main()