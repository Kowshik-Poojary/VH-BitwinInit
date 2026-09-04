import tempfile
import unittest
from pathlib import Path

from leakguard.project_index import build_project_index


class ProjectIndexTests(unittest.TestCase):
    def test_indexes_calls_acquisitions_and_returned_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "db.py"
            path.write_text(
                "def connect_db():\n"
                "    conn = open('db.txt')\n"
                "    return conn\n\n"
                "def use_db():\n"
                "    conn = connect_db()\n"
                "    return conn\n",
                encoding="utf-8",
            )
            index = build_project_index((path,))

        connect = index.by_name("connect_db")[0]
        use = index.by_name("use_db")[0]
        self.assertEqual(connect.acquired_variables, ("conn",))
        self.assertEqual(connect.returned_variables, ("conn",))
        self.assertIn("connect_db", use.calls)


if __name__ == "__main__":
    unittest.main()