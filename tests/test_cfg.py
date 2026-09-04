import ast
import unittest

from leakguard.cfg import CFGBuilder


class CFGBuilderTests(unittest.TestCase):
    @staticmethod
    def _function(source: str) -> ast.FunctionDef:
        tree = ast.parse(source)
        function = tree.body[0]
        assert isinstance(function, ast.FunctionDef)
        return function

    def test_linear_cfg_has_entry_exit_and_statement_nodes(self):
        function = self._function(
            "def test():\n"
            "    f = open('data.txt')\n"
            "    f.close()\n"
        )

        cfg = CFGBuilder().build(function)

        self.assertIsNotNone(cfg.entry)
        self.assertIsNotNone(cfg.exit)
        self.assertGreaterEqual(len(cfg.nodes), 4)
        self.assertEqual(len(cfg.nodes[cfg.entry].successors), 1)

    def test_if_cfg_has_two_branch_successors(self):
        function = self._function(
            "def test(flag):\n"
            "    f = open('data.txt')\n"
            "    if flag:\n"
            "        return\n"
            "    f.close()\n"
        )

        cfg = CFGBuilder().build(function)

        branch_nodes = [
            node for node in cfg.nodes.values() if len(node.successors) > 1
        ]
        self.assertEqual(len(branch_nodes), 1)
        self.assertIsInstance(branch_nodes[0].ast_node, ast.If)

    def test_return_connects_directly_to_exit(self):
        function = self._function(
            "def test():\n"
            "    return\n"
        )

        cfg = CFGBuilder().build(function)

        return_nodes = [
            node
            for node in cfg.nodes.values()
            if isinstance(node.ast_node, ast.Return)
        ]
        self.assertEqual(len(return_nodes), 1)
        self.assertEqual(return_nodes[0].successors, [cfg.exit])

    def test_loop_has_back_edge_and_exit_edge(self):
        function = self._function(
            "def test(items):\n"
            "    for item in items:\n"
            "        print(item)\n"
            "    return\n"
        )

        cfg = CFGBuilder().build(function)

        loop_nodes = [
            node for node in cfg.nodes.values() if isinstance(node.ast_node, ast.For)
        ]
        self.assertEqual(len(loop_nodes), 1)
        self.assertGreaterEqual(len(loop_nodes[0].successors), 2)

    def test_try_finally_routes_return_through_finally(self):
        function = self._function(
            "def test():\n"
            "    try:\n"
            "        return\n"
            "    finally:\n"
            "        cleanup()\n"
        )

        cfg = CFGBuilder().build(function)

        return_nodes = [
            node
            for node in cfg.nodes.values()
            if isinstance(node.ast_node, ast.Return)
        ]
        self.assertEqual(len(return_nodes), 1)
        self.assertNotEqual(return_nodes[0].successors, [cfg.exit])


if __name__ == "__main__":
    unittest.main()
