import unittest

from leakguard.detector import detect
from leakguard.parser import parse_source
from leakguard.resources.detector import ResourceDetector
from leakguard.resources.models import ResourceState
from leakguard.rules import ResourceRule


class ParserDetectorTests(unittest.TestCase):
    def test_configured_sqlite_rule_detects_connection(self):
        scopes = parse_source(
            "import sqlite3\n"
            "def connect():\n"
            "    connection = sqlite3.connect('app.db')\n",
            "db.py",
            (ResourceRule("sqlite3.connect", "SQLite connection"),),
        )

        findings = detect(scopes, "db.py")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].resource_type, "SQLite connection")

    def test_builtin_socket_rule_detects_socket(self):
        scopes = parse_source(
            "import socket\n"
            "def connect():\n"
            "    sock = socket.socket()\n",
            "socket.py",
        )

        findings = detect(scopes, "socket.py")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].resource_type, "Socket")
    def test_resource_detector_records_open_and_close_locations(self):
        scopes = parse_source(
            "def read_file():\n"
            "    f = open('data.txt')\n"
            "    f.close()\n",
            "safe.py",
        )

        resources = ResourceDetector().detect(scopes, "safe.py")

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].resource_id, 1)
        self.assertEqual(resources[0].resource_type, "File")
        self.assertEqual(resources[0].state, ResourceState.CLOSED)
        self.assertEqual(resources[0].opened_line, 2)
        self.assertEqual(resources[0].closed_line, 3)

    def test_resource_detector_keeps_unclosed_resource_open(self):
        scopes = parse_source(
            "def read_file():\n    f = open('data.txt')\n",
            "leak.py",
        )

        resources = ResourceDetector().detect(scopes, "leak.py")

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].state, ResourceState.OPEN)
        self.assertIsNone(resources[0].closed_line)

    def test_reassignment_preserves_the_first_open_resource(self):
        scopes = parse_source(
            "def read_file():\n"
            "    f = open('first.txt')\n"
            "    f = open('second.txt')\n"
            "    f.close()\n",
            "reassigned.py",
        )

        resources = ResourceDetector().detect(scopes, "reassigned.py")

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0].state, ResourceState.OPEN)
        self.assertEqual(resources[0].opened_line, 2)
        self.assertEqual(resources[1].state, ResourceState.CLOSED)
        self.assertEqual(resources[1].opened_line, 3)

    def test_managed_resource_is_recorded_as_closed(self):
        scopes = parse_source(
            "def read_file():\n"
            "    with open('data.txt') as f:\n"
            "        return f.read()\n",
            "managed.py",
        )

        resources = ResourceDetector().detect(scopes, "managed.py")

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].state, ResourceState.CLOSED)

    def test_detects_unclosed_file(self):
        scopes = parse_source(
            "def test():\n    f = open('data.txt')\n    return f.read()\n",
            "leak.py",
        )

        findings = detect(scopes, "leak.py")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].resource_type, "File")
        self.assertEqual(findings[0].variable, "f")
        self.assertEqual(findings[0].opened_line, 2)
        self.assertEqual(findings[0].scope, "test")

    def test_direct_close_is_safe(self):
        scopes = parse_source(
            "def test():\n    f = open('data.txt')\n    f.close()\n",
            "safe.py",
        )

        self.assertEqual(detect(scopes, "safe.py"), ())

    def test_repeated_close_does_not_create_a_false_leak(self):
        scopes = parse_source(
            "def test():\n"
            "    f = open('data.txt')\n"
            "    f.close()\n"
            "    f.close()\n",
            "safe.py",
        )

        self.assertEqual(detect(scopes, "safe.py"), ())

    def test_with_open_is_safe(self):
        scopes = parse_source(
            "def test():\n    with open('data.txt') as f:\n        return f.read()\n",
            "safe.py",
        )

        self.assertEqual(detect(scopes, "safe.py"), ())

    def test_tracks_multiple_resources_independently(self):
        scopes = parse_source(
            "def test():\n"
            "    first = open('first.txt')\n"
            "    second = open('second.txt')\n"
            "    first.close()\n",
            "leak.py",
        )

        findings = detect(scopes, "leak.py")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].variable, "second")
        self.assertEqual(findings[0].opened_line, 3)

    def test_detects_module_scope_acquisition(self):
        scopes = parse_source("f = open('data.txt')\n", "module.py")

        findings = detect(scopes, "module.py")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].scope, "<module>")


if __name__ == "__main__":
    unittest.main()
