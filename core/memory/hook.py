"""
core/memory/hook.py
───────────────────
Context injection hook: queries relevant past memories and injects them with
explicit citation IDs (`[MEM-xxxxxxxx]`) into the agent's system prompt.
"""

from typing import List, Dict, Any, Tuple
from core.memory.store import MemoryStore


def get_memory_context(
    memory_store: MemoryStore,
    query: str,
    project_path: str,
    top_k: int = 3,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Returns (markdown_block, recalled_memory_items).
    """
    if not memory_store:
        return "", []

    memories = memory_store.query_memories(
        query=query,
        project_path=project_path,
        top_k=top_k,
        min_score=0.25,
    )

    if not memories:
        return "", []

    lines = [
        "## Relevant Past Memories & Knowledge Base (Cite IDs like [MEM-xxxxxxxx] when referencing)",
        "The following verified records were retrieved from local SQLite RAG memory:",
    ]

    for m in memories:
        cite = m.get("cite_id") or f"MEM-{str(m.get('id', '00000000'))[:8]}"
        cat = m.get("category", "info").title()
        score = m.get("score", 0.0)
        content = m.get("content", "").strip()
        lines.append(f"- [{cite} | {cat} | score={score:.2f}]: {content}")

    lines.append("")
    return "\n".join(lines), memories
