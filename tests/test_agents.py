"""
tests/test_agents.py
────────────────────
Integration & regression tests for:
  - 3-agent collaboration (PlannerAgent <-> ExecutorAgent <-> CriticAgent)
  - depends_on dependency scheduling & Critic-triggered retry / dynamic replanning
  - Pre-registered HITL approval queues (zero synchronous deadlock)
  - Pre-execution Plan Review HITL with user feedback
  - Uncaught PermissionError fix in _dispatch_tool & sibling directory guard
  - NvidiaProvider tools payload & BM25 long-query RAG recall with [MEM-...] citations
"""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from core.engine import AgentEngine
from core.memory.hook import get_memory_context
from core.memory.store import MemoryStore
from core.providers.base import BaseProvider
from core.providers.nvidia_provider import NvidiaProvider
from tools.files import _is_allowed


class ScriptedMultiAgentProvider(BaseProvider):
    """Deterministic mock provider exercising Planner -> Executor -> Critic -> Replan."""

    def __init__(self):
        super().__init__({})
        self.calls: List[str] = []

    def list_models(self) -> List[str]:
        return ["mock-model"]

    def test_connection(self) -> Dict[str, Any]:
        return {"ok": True, "message": "mock", "models": ["mock-model"]}

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
        enable_thinking: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        sys_txt = messages[0].get("content", "")
        user_txt = messages[-1].get("content", "")
        self.calls.append(sys_txt[:40])

        # 1. PlannerAgent initial plan (deliberately ordered out of ID vs depends_on to test scheduler)
        if "PlannerAgent" in sys_txt and "DYNAMIC REPLANNING" not in user_txt:
            plan = {
                "complexity": "small",
                "reasoning": "Step 2 depends on Step 1",
                "subtasks": [
                    {"id": 2, "title": "Second step", "scope": "Write final file", "depends_on": [1]},
                    {"id": 1, "title": "First step", "scope": "Inspect workspace", "depends_on": []},
                ],
            }
            yield {"type": "token", "content": json.dumps(plan)}
            yield {"type": "done", "content": json.dumps(plan), "thinking": "", "tool_calls": []}
            return

        # 2. PlannerAgent dynamic replan
        if "PlannerAgent" in sys_txt and "DYNAMIC REPLANNING" in user_txt:
            revised = {
                "complexity": "small",
                "reasoning": "Adapted after feedback",
                "subtasks": [
                    {"id": 3, "title": "Recovered write", "scope": "Write note.txt cleanly", "depends_on": []},
                ],
            }
            yield {"type": "token", "content": json.dumps(revised)}
            yield {"type": "done", "content": json.dumps(revised), "thinking": "", "tool_calls": []}
            return

        # 3. CriticAgent evaluation
        if "CriticAgent" in sys_txt:
            # Trigger retry on first attempt of subtask 1, pass thereafter
            if "[1]" in user_txt or "ID: 1" in user_txt:
                if not getattr(self, "_retried_1", False):
                    self._retried_1 = True
                    v = {"satisfied": False, "reason": "Need write_file step.", "next_action": "Write note.txt", "needs_replan": True}
                    yield {"type": "token", "content": json.dumps(v)}
                    yield {"type": "done", "content": json.dumps(v), "thinking": "", "tool_calls": []}
                    return
            v = {"satisfied": True, "reason": "Verified output.", "next_action": "", "needs_replan": False}
            yield {"type": "token", "content": json.dumps(v)}
            yield {"type": "done", "content": json.dumps(v), "thinking": "", "tool_calls": []}
            return

        # 4. ExecutorAgent tool call vs final text
        if messages[-1].get("role") == "tool":
            msg = "Completed subtask cleanly."
            yield {"type": "token", "content": msg}
            yield {"type": "done", "content": msg, "thinking": "", "tool_calls": []}
            return

        tc = {
            "id": "tc_1",
            "type": "function",
            "function": {"name": "write_file", "arguments": json.dumps({"filename": "note.txt", "content": "ok"})},
        }
        yield {"type": "tool_call", "tool_call": tc}
        yield {"type": "done", "content": "", "thinking": "", "tool_calls": [tc]}


class TestMultiAgentAndFixes(unittest.TestCase):
    def test_multi_agent_dag_replan_and_sync_hitl_no_deadlock(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = {
                "provider": "ollama",
                "workspace_roots": [td],
                "output_dir": str(Path(td) / "output"),
                "log_dir": str(Path(td) / "logs"),
                "memory_db_path": str(Path(td) / "mem.db"),
                "seed_knowledge_base": False,
                "safety_mode": "safe",
                "planner_discovery_tools": False,
                "scope_assessment": {"enabled": True, "max_subtasks": 5},
                "satisfaction_loop": {"enabled": True, "max_retries": 2},
            }
            eng = AgentEngine(cfg)
            eng.provider = ScriptedMultiAgentProvider()

            events = []
            # Consume synchronously on same thread (verifies queue pre-registration prevents deadlock!)
            for ev in eng.execute_stream("build a new utility module"):
                events.append(ev)
                if ev["type"] in ("plan_approval_required", "tool_approval_required"):
                    eng.submit_user_response(ev["action_id"], {"approved": True})

            types = [e["type"] for e in events]
            self.assertIn("plan_created", types)
            self.assertIn("plan_approval_required", types)
            self.assertIn("agent_message", types)
            self.assertIn("plan_updated", types)
            self.assertIn("complete", types)

            # Subtask 1 (depends_on=[]) must start before Subtask 2 (depends_on=[1]) despite reverse list order
            starts = [e["subtask"]["id"] for e in events if e["type"] == "subtask_start"]
            self.assertEqual(starts[0], 1)
            self.assertIn(3, starts)  # Replanned subtask 3 executed

    def test_dispatch_tool_catches_permission_error_and_sibling_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            evil = Path(td) / "workspace-evil"
            root.mkdir()
            evil.mkdir()
            secret = evil / "secret.txt"
            secret.write_text("nope", encoding="utf-8")

            # Sibling prefix attack must be rejected
            self.assertFalse(_is_allowed(str(secret), [str(root)]))
            self.assertTrue(_is_allowed(str(root), [str(root)]))

            eng = AgentEngine({
                "provider": "ollama",
                "workspace_roots": [str(root)],
                "output_dir": str(root / "output"),
                "memory_db_path": str(root / "mem.db"),
                "seed_knowledge_base": False,
            })
            res = eng._dispatch_tool("read_file", {"path": str(secret)}, "a1")
            self.assertFalse(res["ok"])
            self.assertEqual(res.get("error_type"), "PermissionError")

    def test_nvidia_provider_includes_tools_in_payload(self):
        captured = {}

        class FakeResp:
            status_code = 200
            def raise_for_status(self): pass
            def iter_lines(self, decode_unicode=True):
                yield 'data: {"choices": [{"delta": {"content": "hi"}}]}'
                yield 'data: [DONE]'

        import core.providers.nvidia_provider as np_mod
        orig_post = np_mod.requests.post
        try:
            def fake_post(url, json=None, headers=None, stream=True, timeout=60):
                captured["payload"] = json
                return FakeResp()
            np_mod.requests.post = fake_post
            prov = NvidiaProvider({"nvidia_api_key": "nvapi-test", "nvidia_pace_delay": 0})
            list(prov.chat_stream([{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {"name": "list_dir"}}]))
            self.assertIn("tools", captured["payload"])
        finally:
            np_mod.requests.post = orig_post

    def test_bm25_long_query_recall_and_citations(self):
        with tempfile.TemporaryDirectory() as td:
            store = MemoryStore(db_path=str(Path(td) / "m.db"), auto_seed=False)
            store.add_memory("Analytics service runs on port 8080 and outputs CSV.", category="architecture", project_path=td)
            store.add_memory("Use pytest for running automated checks.", category="discovery", project_path=td)

            long_q = (
                "We recently decided to review our entire software engineering requirements and deployment setup: "
                "what port and format did the analytics service previously use in this workspace?"
            )
            ctx, items = get_memory_context(store, long_q, td, top_k=3)
            self.assertGreaterEqual(len(items), 1)
            self.assertIn("8080", items[0]["content"])
            self.assertIn("MEM-", ctx)


if __name__ == "__main__":
    unittest.main()
