import ast
import unittest

from leakguard.cfg import CFGBuilder
from leakguard.dataflow import DataflowAnalyzer, ResourceState
from leakguard.parser import parse_source


class DataflowAnalyzerTests(unittest.TestCase):
    @staticmethod
    def _analyze(source: str):
        tree = ast.parse(source)
        function = tree.body[0]
        assert isinstance(function, ast.FunctionDef)
        scopes = parse_source(source)
        scope = next(scope for scope in scopes if scope.name == function.name)
        cfg = CFGBuilder().build(function)
        return DataflowAnalyzer().analyze(cfg, scope.operations)

    def test_safe_close(self):
        result = self._analyze(
            "def test():\n"
            "    f = open('data.txt')\n"
            "    f.close()\n"
        )

        self.assertEqual(result.leaked_variables, ())

    def test_basic_leak(self):
        result = self._analyze("def test():\n    f = open('data.txt')\n")

        self.assertEqual(result.leaked_variables, ("f",))

    def test_early_return_is_a_leak(self):
        result = self._analyze(
            "def test(flag):\n"
            "    f = open('data.txt')\n"
            "    if flag:\n"
            "        return\n"
            "    f.close()\n"
        )

        self.assertEqual(result.leaked_variables, ("f",))

    def test_both_branches_close_safely(self):
        result = self._analyze(
            "def test(flag):\n"
            "    f = open('data.txt')\n"
            "    if flag:\n"
            "        f.close()\n"
            "    else:\n"
            "        f.close()\n"
        )

        self.assertEqual(result.leaked_variables, ())

    def test_one_branch_leaks(self):
        result = self._analyze(
            "def test(flag):\n"
            "    f = open('data.txt')\n"
            "    if flag:\n"
            "        f.close()\n"
            "    else:\n"
            "        return\n"
        )

        self.assertEqual(result.leaked_variables, ("f",))

    def test_state_enum_has_open_and_closed(self):
        self.assertEqual(ResourceState.OPEN.value, "open")
        self.assertEqual(ResourceState.CLOSED.value, "closed")

    def test_try_finally_closes_on_return_path(self):
        result = self._analyze(
            "def test():\n"
            "    f = open('data.txt')\n"
            "    try:\n"
            "        return f.read()\n"
            "    finally:\n"
            "        f.close()\n"
        )

        self.assertEqual(result.leaked_variables, ())

    def test_loop_followed_by_close_is_safe(self):
        result = self._analyze(
            "def test(items):\n"
            "    f = open('data.txt')\n"
            "    for item in items:\n"
            "        print(item)\n"
            "    f.close()\n"
        )

        self.assertEqual(result.leaked_variables, ())

    def test_exception_return_without_finally_is_a_leak(self):
        result = self._analyze(
            "def test():\n"
            "    f = open('data.txt')\n"
            "    try:\n"
            "        work()\n"
            "    except Exception:\n"
            "        return\n"
            "    f.close()\n"
        )

        self.assertEqual(result.leaked_variables, ("f",))

    def test_return_inside_with_is_safe(self):
        result = self._analyze(
            "def test():\n"
            "    with open('data.txt') as f:\n"
            "        return f.read()\n"
        )

        self.assertEqual(result.leaked_variables, ())

    def test_nested_with_is_safe(self):
        result = self._analyze(
            "def test():\n"
            "    with open('first.txt') as first:\n"
            "        with open('second.txt') as second:\n"
            "            return first.read() + second.read()\n"
        )

        self.assertEqual(result.leaked_variables, ())


if __name__ == "__main__":
    unittest.main()
