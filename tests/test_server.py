"""
tests/test_server.py
────────────────────
Unit tests for the Flask REST & SSE endpoints.
"""

import unittest
from server.api import app


class TestServerAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_get_config(self):
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("active_provider", data)

    def test_static_index(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Local Agent", res.data)

    def test_workspace_files(self):
        res = self.client.get("/api/workspace/files")
        self.assertEqual(res.status_code, 200)

    def test_memory_routes(self):
        res = self.client.get("/api/memory")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("memories", data)


if __name__ == "__main__":
    unittest.main()
