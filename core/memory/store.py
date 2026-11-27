"""
core/memory/store.py
────────────────────
100% Local In-Process Hybrid Vector & BM25 Semantic Memory Store.
Uses SQLite for persistence, combining:
  - Genuine BM25 ranking (k1=1.5, b=0.75, corpus IDF, length normalization, stopword filtering)
  - Dense semantic vectors via local Ollama (`nomic-embed-text`) with deterministic
    pure-Python hashed character-trigram vector fallback when Ollama embeddings are unavailable.
"""

import re
import math
import json
import zlib
import sqlite3
import datetime
import uuid
import contextlib
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "how", "i", "if", "in", "into", "is", "it", "its", "me",
    "must", "now", "of", "on", "or", "our", "should", "so", "that", "the",
    "their", "then", "there", "these", "this", "to", "us", "was", "we",
    "what", "when", "where", "which", "who", "will", "with", "you", "your",
}

_FALLBACK_DIM = 128


def _tokenize(text: str) -> List[str]:
    """Lowercased alphanumeric tokenizer with stopword filtering for BM25."""
    raw = re.findall(r"\b[a-zA-Z0-9_.-]{2,}\b", text.lower())
    filtered = [t for t in raw if t not in _STOPWORDS]
    return filtered or raw


def _trigram_embedding(text: str, dim: int = _FALLBACK_DIM) -> List[float]:
    """Deterministic L2-normalized character 3-gram vector fallback (zero external dependencies)."""
    clean = re.sub(r"\s+", " ", text.lower().strip())
    if not clean:
        return []
    vec = [0.0] * dim
    padded = f" {clean} "
    for i in range(max(1, len(padded) - 2)):
        gram = padded[i : i + 3]
        bucket = zlib.crc32(gram.encode("utf-8")) % dim
        vec[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


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
    def __init__(
        self,
        db_path: Optional[str] = None,
        ollama_url: str = "http://127.0.0.1:11434",
        auto_seed: Optional[bool] = None,
    ):
        if not db_path:
            base_dir = Path(__file__).resolve().parent.parent.parent / "data" / "memory"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(base_dir / "memory.db")
            should_seed = True if auto_seed is None else auto_seed
        else:
            self.db_path = db_path
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            should_seed = False if auto_seed is None else auto_seed

        self.ollama_url = ollama_url.rstrip("/")
        self._init_db()
        if should_seed:
            self.seed_knowledge_base()

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

    def seed_knowledge_base(self, kb_path: Optional[str] = None) -> int:
        """Load curated domain knowledge into global store entries if not already present."""
        if not kb_path:
            default_kb = Path(__file__).resolve().parent.parent.parent / "knowledge" / "agent_kb.json"
            if not default_kb.exists():
                return 0
            kb_path = str(default_kb)

        try:
            entries = json.loads(Path(kb_path).read_text(encoding="utf-8"))
        except Exception:
            return 0

        added = 0
        for item in entries:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            with self._get_conn() as conn:
                cur = conn.execute(
                    "SELECT id FROM memories WHERE project_path = '' AND content = ?",
                    (content,),
                )
                if cur.fetchone():
                    continue
            self.add_memory(
                content=content,
                category=item.get("category", "knowledge"),
                project_path="",
                session_id="seed_kb",
                metadata={"kb_id": item.get("id", ""), "source": "knowledge/agent_kb.json"},
            )
            added += 1
        return added

    def compute_embedding(self, text: str) -> Optional[List[float]]:
        """Fetch dense embedding from Ollama `nomic-embed-text`, or fall back to hashed trigram vector."""
        try:
            r = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text},
                timeout=1.5,
            )
            if r.status_code == 200:
                emb = r.json().get("embedding")
                if emb:
                    return emb
        except Exception:
            pass
        return _trigram_embedding(text)

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
        Hybrid search combining normalized BM25 ranking and cosine vector similarity.
        """
        query = query.strip()
        if not query:
            return []

        query_tokens = _tokenize(query)
        unique_q_tokens = set(query_tokens)
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

        if not rows:
            return []

        # Corpus statistics for Okapi BM25
        docs_tokens = [_tokenize(r["content"]) for r in rows]
        n_docs = len(docs_tokens)
        avgdl = sum(len(dt) for dt in docs_tokens) / max(1, n_docs)
        df: Dict[str, int] = {}
        for dt in docs_tokens:
            for term in set(dt):
                df[term] = df.get(term, 0) + 1

        k1 = 1.5
        b = 0.75
        bm25_raw: List[float] = []
        for dt in docs_tokens:
            tf = Counter(dt)
            dl = max(1, len(dt))
            score = 0.0
            for term in unique_q_tokens:
                if term not in tf:
                    continue
                n_qi = df.get(term, 0)
                idf = math.log(1.0 + (n_docs - n_qi + 0.5) / (n_qi + 0.5))
                freq = tf[term]
                denom = freq + k1 * (1.0 - b + b * (dl / max(1.0, avgdl)))
                score += idf * ((freq * (k1 + 1.0)) / denom)
            bm25_raw.append(score)

        max_bm25 = max(bm25_raw) if bm25_raw else 0.0

        scored = []
        for idx, r in enumerate(rows):
            # Normalize BM25 relative to top corpus match & query saturation so long queries don't dilute to 0
            raw_b = bm25_raw[idx]
            bm25_norm = (raw_b / (raw_b + 1.2)) if raw_b > 0 else 0.0
            if max_bm25 > 0 and raw_b > 0:
                bm25_norm = max(bm25_norm, 0.85 * (raw_b / max_bm25))

            # Vector cosine similarity (uses compatible embedding dimension)
            vector_score = 0.0
            r_emb = None
            if r["embedding"]:
                try:
                    r_emb = json.loads(r["embedding"])
                except Exception:
                    r_emb = None
            if query_emb and r_emb and len(query_emb) == len(r_emb):
                vector_score = max(0.0, _cosine_similarity(query_emb, r_emb))
            elif query_emb and len(query_emb) == _FALLBACK_DIM:
                fb_emb = _trigram_embedding(r["content"])
                vector_score = max(0.0, _cosine_similarity(query_emb, fb_emb))

            # Hybrid fusion
            if raw_b > 0:
                final_score = (0.65 * bm25_norm) + (0.35 * vector_score)
            else:
                final_score = 0.55 * vector_score

            # Slight preference for project-local memories over global seeded KB on ties
            if project_path and r["project_path"] == project_path and final_score > 0:
                final_score = min(1.0, final_score + 0.04)

            if final_score >= min_score:
                scored.append({
                    "id": r["id"],
                    "cite_id": f"MEM-{r['id'][:8]}",
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
                    "SELECT * FROM memories WHERE project_path = ? OR project_path = '' ORDER BY timestamp DESC LIMIT ?",
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
