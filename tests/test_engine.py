"""
tests/test_engine.py
────────────────────
Unit tests for the AgentEngine, Scratchpad, and Tool execution.
"""

import unittest
import tempfile
from pathlib import Path
from core.engine import AgentEngine
from core.scratchpad import ScratchpadManager


class TestEngine(unittest.TestCase):
    def test_scratchpad(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            sm = ScratchpadManager(out_dir, [tmpdir])

            sm.load_or_init("Test Goal", [{"id": 1, "title": "Subtask 1", "scope": "Scope 1"}])
            sm.add_discovery("Found config file at ./config.yaml")
            sm.add_note("Remember to run tests")
            sm.add_file(str(out_dir / "test.txt"))

            view = sm.build_agent_view()
            self.assertIn("Test Goal", view)
            self.assertIn("Subtask 1", view)
            self.assertIn("Found config file", view)
            self.assertTrue(sm.path.exists())

    def test_engine_init_and_tool_dispatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "provider": "ollama",
                "model": "test-model",
                "workspace_roots": [tmpdir],
                "output_dir": tmpdir,
                "safety_mode": "safe",
            }
            engine = AgentEngine(config)

            # Create a test file
            test_file = Path(tmpdir) / "sample.txt"
            test_file.write_text("Hello World\nLine 2\nLine 3", encoding="utf-8")

            # Test list_dir
            res_list = engine._dispatch_tool("list_dir", {"path": tmpdir}, "action_1")
            self.assertTrue(res_list.get("ok"))
            self.assertTrue(any(e["name"] == "sample.txt" for e in res_list.get("entries", [])))

            # Test stat_file
            res_stat = engine._dispatch_tool("stat_file", {"path": str(test_file)}, "action_2")
            self.assertTrue(res_stat.get("ok"))
            self.assertEqual(res_stat.get("total_lines"), 3)

            # Test read_file_lines
            res_lines = engine._dispatch_tool(
                "read_file_lines",
                {"path": str(test_file), "start_line": 1, "end_line": 2},
                "action_3",
            )
            self.assertTrue(res_lines.get("ok"))
            self.assertIn("Hello World", res_lines.get("content", ""))


if __name__ == "__main__":
    unittest.main()
