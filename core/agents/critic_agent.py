"""
core/agents/critic_agent.py
───────────────────────────
Specialized CriticAgent responsible for verifying ExecutorAgent outputs,
inspecting workspace artifacts via read-only tools when needed, and deciding
whether a subtask passes, needs a targeted retry, or requires dynamic replanning.
"""

import json
import re
from typing import Any, Callable, Dict, Generator, List, Optional
from core.providers.base import BaseProvider
from core.tools_schema import TOOLS_SCHEMA

CRITIC_TOOL_NAMES = {"stat_file", "read_file", "read_file_lines", "list_dir"}

CRITIC_PROMPT = """\
You are CriticAgent in a multi-agent system (reviewing ExecutorAgent's work for PlannerAgent).
Judge whether ExecutorAgent genuinely satisfied the assigned sub-task based on observed evidence.

Original User Request:
{original_request}

Current Sub-Task:
  ID: {subtask_id}
  Title: {title}
  Scope: {scope}

ExecutorAgent Output & Observed Tool Evidence:
---
{agent_summary}
---

Verification rules:
- You have read-only inspection tools (stat_file, read_file, read_file_lines, list_dir) to check created/edited files if needed.
- Mark satisfied=false if a required tool failed without recovery, an output file was not actually created/verified, or the response contradicts observed data.
- Set needs_replan=true ONLY if the subtask itself is blocked by wrong assumptions, missing prerequisites, or changed requirements that require PlannerAgent to revise remaining steps.
- Otherwise, if a targeted retry can fix the issue, set needs_replan=false and provide a concrete `next_action`.

Reply with ONLY a valid JSON object:
{{
  "satisfied": true | false,
  "reason": "one concise sentence grounded in tool/file evidence",
  "next_action": "specific instruction for ExecutorAgent retry or PlannerAgent replan (empty if satisfied)",
  "needs_replan": false
}}
"""


def _parse_verdict(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {
            "satisfied": True,
            "reason": "Critic parse skipped — assuming done.",
            "next_action": "",
            "needs_replan": False,
        }
    try:
        data = json.loads(match.group())
        return {
            "satisfied": bool(data.get("satisfied", True)),
            "reason": str(data.get("reason", "Evaluated.")),
            "next_action": str(data.get("next_action", "")),
            "needs_replan": bool(data.get("needs_replan", False)),
        }
    except Exception:
        return {
            "satisfied": True,
            "reason": "Critic JSON invalid — assuming done.",
            "next_action": "",
            "needs_replan": False,
        }


class CriticAgent:
    """Independent Critic & Verifier agent with read-only workspace inspection tools."""

    def __init__(self, temperature: float = 0.1, max_verify_turns: int = 2):
        self.temperature = temperature
        self.max_verify_turns = max_verify_turns
        self.critic_tools = [
            t for t in TOOLS_SCHEMA if t.get("function", {}).get("name") in CRITIC_TOOL_NAMES
        ]

    def evaluate_stream(
        self,
        provider: BaseProvider,
        subtask: Dict[str, Any],
        report: Dict[str, Any],
        original_request: str = "",
        tool_runner: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], Generator[Dict[str, Any], None, Dict[str, Any]]]] = None,
    ) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        """Evaluates an ExecutionReport, optionally using read-only tools to verify files."""
        summary_parts: List[str] = []
        last_response = report.get("last_response", "")
        if last_response and last_response != "(no response)":
            summary_parts.append(f"ExecutorAgent response:\n{last_response[:1000]}")

        tool_history = report.get("tool_records", [])
        if tool_history:
            lines = [
                f"  -> {t.get('name')} (ok={t.get('ok')}){': ' + str(t.get('error'))[:120] if t.get('error') else ''}"
                for t in tool_history[-6:]
            ]
            summary_parts.append("Tools executed:\n" + "\n".join(lines))

        evidence = report.get("evidence_snippets", [])
        if evidence:
            summary_parts.append("Tool evidence:\n" + "\n".join(f"  * {e}" for e in evidence[-6:]))

        agent_summary = "\n\n".join(summary_parts) if summary_parts else "(no output)"

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": "You are CriticAgent. Verify subtask completion objectively and reply only with JSON."},
            {
                "role": "user",
                "content": CRITIC_PROMPT.format(
                    original_request=original_request or "(not specified)",
                    subtask_id=subtask.get("id", "?"),
                    title=subtask.get("title", "Unknown"),
                    scope=subtask.get("scope", ""),
                    agent_summary=agent_summary[:2500],
                ),
            },
        ]

        tools_arg = self.critic_tools if tool_runner is not None else None

        for turn in range(self.max_verify_turns if tools_arg else 1):
            full_text: List[str] = []
            tool_calls: List[Dict[str, Any]] = []

            for chunk in provider.chat_stream(
                messages,
                tools=tools_arg if turn < self.max_verify_turns - 1 else None,
                temperature=self.temperature,
                enable_thinking=False,
            ):
                ctype = chunk.get("type")
                if ctype == "token":
                    full_text.append(chunk.get("content", ""))
                elif ctype == "tool_call":
                    tool_calls.append(chunk.get("tool_call"))
                elif ctype == "done" and chunk.get("content") and not full_text:
                    full_text = [chunk["content"]]

            raw = "".join(full_text).strip()
            if tool_calls and tool_runner is not None and turn < self.max_verify_turns - 1:
                messages.append({"role": "assistant", "content": raw, "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments", {})
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                    except Exception:
                        args = {}
                    res = yield from tool_runner(name, args, tc)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"critic_{turn}_{name}"),
                        "name": name,
                        "content": json.dumps(res, ensure_ascii=False),
                    })
                continue

            return _parse_verdict(raw)

        return {"satisfied": True, "reason": "Critic completed.", "next_action": "", "needs_replan": False}
