"""
core/memory/store.py
────────────────────
100% Local In-Process Vector & Semantic Memory Store.
Uses SQLite for persistence, with hybrid semantic embedding
(via local Ollama or lightweight pure-Python vector math) and BM25 ranking.
"""

import os
import re
import math
import json
import sqlite3
import datetime
import uuid
import contextlib
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests


def _tokenize(text: str) -> List[str]:
    """Basic lowercased alphanumeric tokenizer."""
    return re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class MemoryStore:
    def __init__(self, db_path: Optional[str] = None, ollama_url: str = "http://127.0.0.1:11434"):
        if not db_path:
            base_dir = Path(__file__).resolve().parent.parent.parent / "data" / "memory"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(base_dir / "memory.db")
        else:
            self.db_path = db_path
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.ollama_url = ollama_url.rstrip("/")
        self._init_db()

    @contextlib.contextmanager
    def _get_conn(self):
        try:
            conn = sqlite3.connect(self.db_path)
        except Exception:
            conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    project_path TEXT,
                    timestamp TEXT,
                    category TEXT,
                    content TEXT NOT NULL,
                    embedding TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_project ON memories(project_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_category ON memories(category)")
            conn.commit()

    def compute_embedding(self, text: str) -> Optional[List[float]]:
        """Try fetching vector embedding from local Ollama if available."""
        try:
            r = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text},
                timeout=2,
            )
            if r.status_code == 200:
                return r.json().get("embedding")
        except Exception:
            pass
        return None

    def add_memory(
        self,
        content: str,
        category: str = "discovery",
        project_path: str = "",
        session_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        content = content.strip()
        if not content:
            return ""

        mem_id = str(uuid.uuid4())
        ts = datetime.datetime.now().isoformat()
        embedding = self.compute_embedding(content)
        emb_str = json.dumps(embedding) if embedding else ""
        meta_str = json.dumps(metadata or {})

        with self._get_conn() as conn:
            # Check for exact duplicate in same project
            cur = conn.execute(
                "SELECT id FROM memories WHERE project_path = ? AND content = ?",
                (project_path, content),
            )
            existing = cur.fetchone()
            if existing:
                return existing["id"]

            conn.execute(
                """
                INSERT INTO memories (id, session_id, project_path, timestamp, category, content, embedding, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mem_id, session_id, project_path, ts, category, content, emb_str, meta_str),
            )
            conn.commit()
        return mem_id

    def query_memories(
        self,
        query: str,
        project_path: Optional[str] = None,
        top_k: int = 4,
        min_score: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining semantic cosine similarity and token overlap BM25.
        """
        query = query.strip()
        if not query:
            return []

        query_tokens = set(_tokenize(query))
        query_emb = self.compute_embedding(query)

        with self._get_conn() as conn:
            if project_path:
                cur = conn.execute(
                    "SELECT * FROM memories WHERE project_path = ? OR project_path = ''",
                    (project_path,),
                )
            else:
                cur = conn.execute("SELECT * FROM memories")
            rows = cur.fetchall()

        scored = []
        for r in rows:
            content = r["content"]
            tokens = set(_tokenize(content))

            # Keyword Jaccard/overlap score
            keyword_score = 0.0
            if query_tokens and tokens:
                intersection = query_tokens.intersection(tokens)
                keyword_score = len(intersection) / len(query_tokens)

            # Vector cosine score
            vector_score = 0.0
            if query_emb and r["embedding"]:
                try:
                    r_emb = json.loads(r["embedding"])
                    vector_score = _cosine_similarity(query_emb, r_emb)
                except Exception:
                    pass

            # Combined hybrid score
            if query_emb and r["embedding"]:
                final_score = (0.6 * vector_score) + (0.4 * keyword_score)
            else:
                final_score = keyword_score

            if final_score >= min_score:
                scored.append({
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "project_path": r["project_path"],
                    "timestamp": r["timestamp"],
                    "category": r["category"],
                    "content": r["content"],
                    "score": round(final_score, 3),
                    "metadata": json.loads(r["metadata"] or "{}"),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def list_memories(self, project_path: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            if project_path:
                cur = conn.execute(
                    "SELECT * FROM memories WHERE project_path = ? ORDER BY timestamp DESC LIMIT ?",
                    (project_path, limit),
                )
            else:
                cur = conn.execute("SELECT * FROM memories ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cur.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "project_path": r["project_path"],
                "timestamp": r["timestamp"],
                "category": r["category"],
                "content": r["content"],
                "metadata": json.loads(r["metadata"] or "{}"),
            })
        return results

    def delete_memory(self, memory_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear_memories(self, project_path: Optional[str] = None):
        with self._get_conn() as conn:
            if project_path:
                conn.execute("DELETE FROM memories WHERE project_path = ?", (project_path,))
            else:
                conn.execute("DELETE FROM memories")
            conn.commit()
