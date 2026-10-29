"""
core/memory/indexer.py
──────────────────────
Harvester that records scratchpad discoveries, solutions, and notes
into the persistent long-term memory store.
"""

from typing import Dict, Any, List
from core.memory.store import MemoryStore


def harvest_session_memory(
    memory_store: MemoryStore,
    project_path: str,
    session_id: str,
    goal: str,
    discoveries: List[str],
    notes: List[str],
    solution_summary: str = "",
):
    """Save key knowledge points to long-term memory."""
    if not memory_store:
        return

    # 1. Index Key Discoveries
    for d in discoveries:
        d_clean = d.strip("- ").strip()
        if len(d_clean) > 8:
            memory_store.add_memory(
                content=d_clean,
                category="discovery",
                project_path=project_path,
                session_id=session_id,
            )

    # 2. Index Architecture / Reminders from Notes
    for n in notes:
        n_clean = n.strip("- ").strip()
        if len(n_clean) > 8:
            memory_store.add_memory(
                content=n_clean,
                category="architecture",
                project_path=project_path,
                session_id=session_id,
            )

    # 3. Index completed goal summary if provided
    if solution_summary and len(solution_summary.strip()) > 15:
        memory_store.add_memory(
            content=f"Goal: {goal} | Resolution: {solution_summary.strip()[:400]}",
            category="solution",
            project_path=project_path,
            session_id=session_id,
        )
