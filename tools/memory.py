"""
tools/memory.py
───────────────
Agent tool for on-demand long-term memory retrieval with citation IDs.
"""

from typing import Dict, Any
from core.memory.store import MemoryStore

_MEMORY_STORE: MemoryStore = None


def set_memory_store(store: MemoryStore):
    global _MEMORY_STORE
    _MEMORY_STORE = store


def recall_memory(query: str, project_path: str = "") -> Dict[str, Any]:
    """
    Search long-term memory for past project decisions, bug fixes, or architecture insights.
    """
    global _MEMORY_STORE
    if not _MEMORY_STORE:
        _MEMORY_STORE = MemoryStore()

    results = _MEMORY_STORE.query_memories(query=query, project_path=project_path, top_k=5)
    return {
        "ok": True,
        "query": query,
        "count": len(results),
        "matches": [
            {
                "cite_id": r.get("cite_id") or f"MEM-{str(r['id'])[:8]}",
                "category": r["category"],
                "content": r["content"],
                "score": r["score"],
                "timestamp": r["timestamp"],
            }
            for r in results
        ],
    }
