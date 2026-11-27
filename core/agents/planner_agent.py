"""
core/agents/planner_agent.py
────────────────────────────
Specialized Planner & Requirements Architect Agent.
Capabilities:
  1. Workspace-aware task decomposition into dependency-linked subtasks (depends_on DAG).
  2. Optional read-only pre-plan inspection & ambiguity detection (ask_user, recall_memory, list_dir, read_file).
  3. Dynamic replanning (replan) when CriticAgent rejects, tools fail, or user requirements change.
"""

import json
import re
from typing import Any, Callable, Dict, Generator, List, Optional
from core.providers.base import BaseProvider
from core.tools_schema import TOOLS_SCHEMA

PLANNER_TOOL_NAMES = {"list_dir", "find_similar_files", "stat_file", "read_file", "recall_memory", "ask_user"}

PLANNER_SYSTEM_PROMPT = """\
You are the PlannerAgent in a multi-agent engineering system (working alongside ExecutorAgent and CriticAgent).
Your job is to inspect the request, check for missing critical requirements or workspace constraints, and decompose work into an accurate dependency DAG.

Guidelines:
- You have read-only discovery tools (list_dir, find_similar_files, stat_file, read_file, recall_memory) and ask_user.
- Only call tools if the workspace snapshot or request lacks critical details needed to plan accurately; otherwise output the JSON plan directly.
- If the request is genuinely missing mandatory choices (e.g., ambiguous target file, unknown format when explicitly unspecified), call ask_user BEFORE locking in the plan.
- Break complex requests into 1–{max_subtasks} atomic, self-contained subtasks with explicit `depends_on` IDs.
- Include exact verified file paths in subtask `scope` (never invent paths like `/output/foo` unless confirmed).
- Return ONLY a valid JSON object:
{{
  "complexity": "small|medium|large",
  "reasoning": "one concise sentence explaining complexity and dependency structure",
  "subtasks": [
    {{"id": 1, "title": "...", "scope": "...", "depends_on": []}},
    {{"id": 2, "title": "...", "scope": "...", "depends_on": [1]}}
  ]
}}
"""

REPLAN_PROMPT = """\
You are the PlannerAgent performing DYNAMIC REPLANNING because execution encountered feedback, a failure, or changed user requirements.

Original Request:
{request}

Workspace Snapshot:
{workspace_snapshot}

Completed Subtasks (DO NOT repeat these):
{completed_summary}

Failed / Blocked Subtask or Trigger:
{trigger_context}

CriticAgent / User Feedback:
{feedback}

Recent Agent Collaboration Messages:
{bus_log}

Scratchpad State:
{scratchpad_context}

Revise ONLY the remaining/next subtasks needed to achieve the updated goal safely.
Use new sequential IDs starting at {next_id}, setting `depends_on` only to remaining IDs (or `[]` if ready immediately).
Return ONLY a valid JSON object:
{{
  "complexity": "small|medium|large",
  "reasoning": "one sentence explaining how the plan adapted to the feedback/failure",
  "subtasks": [
    {{"id": {next_id}, "title": "...", "scope": "...", "depends_on": []}}
  ]
}}
"""


def _extract_json_plan(raw: str) -> Optional[Dict[str, Any]]:
    raw = (raw or "").strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        if isinstance(data.get("subtasks"), list) and data["subtasks"]:
            # Normalize fields defensively
            norm = []
            for idx, st in enumerate(data["subtasks"], 1):
                if not isinstance(st, dict):
                    continue
                sid = int(st.get("id", idx))
                deps = st.get("depends_on", [])
                if not isinstance(deps, list):
                    deps = []
                norm.append({
                    "id": sid,
                    "title": str(st.get("title", f"Subtask {sid}")),
                    "scope": str(st.get("scope", st.get("title", ""))),
                    "depends_on": [int(d) for d in deps if isinstance(d, (int, str)) and str(d).isdigit()],
                })
            if norm:
                data["subtasks"] = norm
                return data
    except Exception:
        pass
    return None


class PlannerAgent:
    """Specialized PlannerAgent supporting tool-backed discovery and dynamic replanning."""

    def __init__(self, max_subtasks: int = 12, max_discovery_turns: int = 3):
        self.max_subtasks = max_subtasks
        self.max_discovery_turns = max_discovery_turns
        self.planner_tools = [
            t for t in TOOLS_SCHEMA if t.get("function", {}).get("name") in PLANNER_TOOL_NAMES
        ]

    def plan_stream(
        self,
        provider: BaseProvider,
        user_request: str,
        workspace_snapshot: str,
        scratchpad_context: str = "",
        memory_context: str = "",
        tool_runner: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], Generator[Dict[str, Any], None, Dict[str, Any]]]] = None,
        enable_discovery_tools: bool = True,
    ) -> Generator[Dict[str, Any], None, Optional[Dict[str, Any]]]:
        """
        Yields intermediate tool/thinking events while constructing the subtask DAG.
        Returns the parsed plan dict (or None on parse failure).
        """
        sys_msg = PLANNER_SYSTEM_PROMPT.format(max_subtasks=self.max_subtasks)
        user_parts = [
            f"User Request:\n{user_request}",
            f"Top-Level Workspace Snapshot:\n{workspace_snapshot}",
            f"Current Scratchpad Context:\n{scratchpad_context or '(nothing done yet)'}",
        ]
        if memory_context:
            user_parts.append(f"Recalled Long-Term Memory:\n{memory_context}")

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]

        tools_arg = self.planner_tools if (enable_discovery_tools and tool_runner is not None) else None

        for turn in range(self.max_discovery_turns if tools_arg else 1):
            full_text: List[str] = []
            tool_calls: List[Dict[str, Any]] = []

            for chunk in provider.chat_stream(messages, tools=tools_arg, temperature=0.2, enable_thinking=False):
                ctype = chunk.get("type")
                if ctype == "token":
                    full_text.append(chunk.get("content", ""))
                elif ctype == "tool_call":
                    tool_calls.append(chunk.get("tool_call"))
                elif ctype == "done":
                    if chunk.get("content") and not full_text:
                        full_text = [chunk["content"]]
                elif ctype == "error":
                    yield {"type": "status", "message": f"PlannerAgent fallback: {chunk.get('error', '')}"}
                    return None

            raw = "".join(full_text).strip()
            if tool_calls and tool_runner is not None and turn < self.max_discovery_turns - 1:
                messages.append({"role": "assistant", "content": raw, "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments", {})
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                    except Exception:
                        args = {}
                    result = yield from tool_runner(name, args, tc)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"planner_{turn}_{name}"),
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                continue

            plan = _extract_json_plan(raw)
            if plan:
                return plan

        return None

    def replan(
        self,
        provider: BaseProvider,
        user_request: str,
        workspace_snapshot: str,
        completed_subtasks: List[Dict[str, Any]],
        trigger_context: str,
        feedback: str,
        bus_log: str = "",
        scratchpad_context: str = "",
        next_id: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """Generate a revised remaining plan adapting to failure or new feedback."""
        completed_summary = "\n".join(
            f"- [{st['id']}] {st['title']}" for st in completed_subtasks
        ) or "(none yet)"

        prompt = REPLAN_PROMPT.format(
            request=user_request,
            workspace_snapshot=workspace_snapshot,
            completed_summary=completed_summary,
            trigger_context=trigger_context,
            feedback=feedback,
            bus_log=bus_log or "(none)",
            scratchpad_context=scratchpad_context or "(none)",
            next_id=next_id,
        )
        messages = [
            {"role": "system", "content": "You are PlannerAgent. Reply ONLY with the revised JSON plan."},
            {"role": "user", "content": prompt},
        ]

        full_text: List[str] = []
        for chunk in provider.chat_stream(messages, tools=None, temperature=0.2, enable_thinking=False):
            if chunk.get("type") == "token":
                full_text.append(chunk.get("content", ""))
            elif chunk.get("type") == "done" and chunk.get("content") and not full_text:
                full_text = [chunk["content"]]

        return _extract_json_plan("".join(full_text))
