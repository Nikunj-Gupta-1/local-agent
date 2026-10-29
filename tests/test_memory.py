"""
tests/test_memory.py
────────────────────
Unit tests for the Long-Term Memory RAG system.
"""

import unittest
import tempfile
from pathlib import Path
from core.memory.store import MemoryStore
from core.memory.indexer import harvest_session_memory
from core.memory.hook import get_memory_context


class TestMemoryRAG(unittest.TestCase):
    def test_memory_store_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_memory.db")
            store = MemoryStore(db_path=db_path)

            # 1. Add memories
            id1 = store.add_memory(
                content="Project uses pytest for test runs and python 3.11",
                category="architecture",
                project_path="/test/project",
            )
            self.assertTrue(bool(id1))

            id2 = store.add_memory(
                content="Database connection timeout should be set to 60s",
                category="decision",
                project_path="/test/project",
            )
            self.assertTrue(bool(id2))

            # 2. Query memories
            results = store.query_memories("pytest python test", project_path="/test/project")
            self.assertGreaterEqual(len(results), 1)
            self.assertIn("pytest", results[0]["content"])

            # 3. List and Delete
            all_mems = store.list_memories(project_path="/test/project")
            self.assertEqual(len(all_mems), 2)

            deleted = store.delete_memory(id1)
            self.assertTrue(deleted)

            remaining = store.list_memories(project_path="/test/project")
            self.assertEqual(len(remaining), 1)

    def test_harvest_and_hook(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_memory.db")
            store = MemoryStore(db_path=db_path)

            harvest_session_memory(
                memory_store=store,
                project_path="/app",
                session_id="session_123",
                goal="Refactor authentication layer",
                discoveries=["Auth token is stored in HTTP-only cookie with samesite=strict"],
                notes=["Make sure to test CORS header allow-credentials"],
                solution_summary="Auth cookies migrated successfully.",
            )

            ctx, items = get_memory_context(store, "How is auth token stored?", "/app")
            self.assertGreaterEqual(len(items), 1)
            self.assertIn("Relevant Past Memories", ctx)
            self.assertIn("HTTP-only cookie", ctx)


if __name__ == "__main__":
    unittest.main()
