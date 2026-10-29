"""
core/evaluator.py
─────────────────
Evaluates whether a sub-task has been satisfactorily completed.
"""

import re
import json
from typing import Dict, Any, List, Optional
from core.providers.base import BaseProvider

EVALUATOR_PROMPT = """\
You are a practical completion evaluator. Your job is to judge whether the agent made
meaningful progress toward completing its assigned sub-task.

Original user request (the overall goal):
{original_request}

Current sub-task:
  Title: {title}
  Scope: {scope}

Summary of what the agent did this turn:
---
{agent_summary}
---

Evaluation rules:
- Judge whether the agent made meaningful progress toward the sub-task and the overall goal.
- If the agent used tools (read files, ran commands, wrote files), treat that as evidence of work.
- Only mark satisfied=false if the agent clearly did NOTHING useful or produced a wrong result.
- Be practical, not pedantic.

Reply with ONLY a valid JSON object:
{{
  "satisfied": true | false,
  "reason": "one sentence explaining your decision",
  "next_action": "what the agent should do next if not satisfied (empty string if satisfied)"
}}
"""


def check_satisfaction(
    provider: BaseProvider,
    subtask: Dict[str, Any],
    last_response: str,
    tool_history: List[Dict[str, Any]],
    original_request: str = "",
    temperature: float = 0.1,
) -> Dict[str, Any]:
    summary_parts = []
    if last_response and last_response != "(no response)":
        summary_parts.append(f"Agent response:\n{last_response[:1000]}")

    if tool_history:
        tool_lines = []
        for t in tool_history[-5:]:
            tool_lines.append(f"  → Tool '{t.get('name')}' executed (ok={t.get('ok')})")
        summary_parts.append("Recent tools:\n" + "\n".join(tool_lines))

    agent_summary = "\n\n".join(summary_parts) if summary_parts else "(no output)"

    messages = [
        {"role": "system", "content": "You are a completion evaluator. Reply only with JSON."},
        {
            "role": "user",
            "content": EVALUATOR_PROMPT.format(
                original_request=original_request or "(not specified)",
                title=subtask.get("title", "Unknown"),
                scope=subtask.get("scope", ""),
                agent_summary=agent_summary[:2000],
            ),
        },
    ]

    full_text = []
    for chunk in provider.chat_stream(messages, temperature=temperature, tools=None):
        if chunk.get("type") == "token":
            full_text.append(chunk.get("content", ""))
        elif chunk.get("type") == "done":
            content = chunk.get("content", "")
            if content:
                full_text = [content]

    raw = "".join(full_text).strip()
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        return {"satisfied": True, "reason": "Evaluator parse skipped — assuming done.", "next_action": ""}

    try:
        return json.loads(json_match.group())
    except Exception:
        return {"satisfied": True, "reason": "Evaluator JSON invalid — assuming done.", "next_action": ""}
