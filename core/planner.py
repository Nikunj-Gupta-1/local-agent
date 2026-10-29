"""
core/planner.py
───────────────
Autonomous task decomposition pass. Breaks complex requests into
ordered, atomic subtasks.
"""

import re
import json
from typing import Optional, List, Dict, Any
from core.providers.base import BaseProvider

PLANNER_PROMPT = """\
You are a planning assistant. Do NOT execute anything yet.

The user has made the following request:
{request}

Here is the top-level workspace structure:
{workspace_snapshot}

Current session context (what has already been done this session — use this to avoid re-doing completed work):
{scratchpad_context}

Your job:
1. Estimate the complexity of this task (small / medium / large).
2. Decompose the task into an ordered list of focused sub-tasks.
   - Each sub-task must be completable in a single focused LLM session using at most 50% of the context window.
   - Each sub-task should be atomic, self-contained, and clearly scoped.
   - If work is already done (shown in session context above), skip it or acknowledge it — do NOT re-plan it.
   - Aim for 1–{max_subtasks} sub-tasks. Do not over-decompose simple tasks.
3. Return ONLY a valid JSON object in this exact format (no markdown, no commentary):

{{
  "complexity": "small|medium|large",
  "reasoning": "one sentence explaining your complexity estimate",
  "subtasks": [
    {{"id": 1, "title": "...", "scope": "...", "depends_on": []}},
    {{"id": 2, "title": "...", "scope": "...", "depends_on": [1]}}
  ]
}}
"""


def run_planner_pass(
    provider: BaseProvider,
    user_request: str,
    workspace_snapshot: str,
    scratchpad_context: str = "",
    max_subtasks: int = 15,
) -> Optional[Dict[str, Any]]:
    """
    Decomposes user request into subtasks.
    Returns: {"complexity": str, "reasoning": str, "subtasks": list[dict]} or None
    """
    messages = [
        {"role": "system", "content": "You are a concise task planning assistant. Reply only with the requested JSON."},
        {
            "role": "user",
            "content": PLANNER_PROMPT.format(
                request=user_request,
                workspace_snapshot=workspace_snapshot,
                scratchpad_context=scratchpad_context or "(nothing done yet)",
                max_subtasks=max_subtasks,
            ),
        },
    ]

    full_text = []
    for chunk in provider.chat_stream(messages, temperature=0.2, tools=None):
        if chunk.get("type") == "token":
            full_text.append(chunk.get("content", ""))
        elif chunk.get("type") == "done":
            content = chunk.get("content", "")
            if content:
                full_text = [content]

    raw = "".join(full_text).strip()
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
        if "subtasks" in data and isinstance(data["subtasks"], list):
            return data
    except Exception:
        pass
    return None
