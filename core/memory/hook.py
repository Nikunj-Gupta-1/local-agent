"""
core/memory/hook.py
───────────────────
Context injection hook: queries relevant past memories and injects them
into the agent's system prompt prior to task execution.
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
        "## Relevant Past Memories & Project Context",
        "The following memories were recalled from previous sessions in this project:",
    ]

    for m in memories:
        cat = m.get("category", "info").title()
        content = m.get("content", "").strip()
        lines.append(f"- [{cat}]: {content}")

    lines.append("")
    return "\n".join(lines), memories
