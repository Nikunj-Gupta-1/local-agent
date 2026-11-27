"""
core/agents/executor_agent.py
─────────────────────────────
Specialized ExecutorAgent responsible for carrying out scoped subtasks (or DIRECT turns)
using tools, recording grounded evidence, and reporting structured results to CriticAgent.
"""

import json
from typing import Any, Callable, Dict, Generator, List, Optional
from core.providers.base import BaseProvider
from core.tools_schema import TOOLS_SCHEMA


def _summarize_tool_result(name: str, result: Dict[str, Any]) -> str:
    """Extract a compact grounded evidence line so downstream subtasks keep verified facts."""
    ok = result.get("ok", True)
    if not ok:
        return f"{name} -> ERROR: {result.get('error') or result.get('reason') or 'failed'}"
    if name in ("read_file", "read_file_lines"):
        content = str(result.get("content", "")).strip().replace("\n", "\\n")
        return f"{name}({result.get('path', '')}) -> {content[:350]}"
    if name == "write_file":
        return f"write_file -> {result.get('path', '')} ({result.get('bytes_written', 0)}B)"
    if name == "edit_file_lines":
        return f"edit_file_lines({result.get('path', '')}) -> lines {result.get('start_line')}-{result.get('end_line')}"
    if name == "run_command":
        code = result.get("exit_code")
        out = (result.get("stdout") or result.get("stderr") or "").strip().replace("\n", " ")
        return f"run_command(`{result.get('cmd', '')}`) -> exit={code} {out[:250]}"
    if name == "ask_user":
        return f"ask_user -> user answered: {result.get('user_answer', '')}"
    if name == "recall_memory":
        return f"recall_memory -> {result.get('count', 0)} matches"
    return f"{name} -> ok=True"


class ExecutorAgent:
    """Tool-using execution specialist that produces structured ExecutionReports."""

    def __init__(self, max_turns_direct: int = 5, max_turns_subtask: int = 10):
        self.max_turns_direct = max_turns_direct
        self.max_turns_subtask = max_turns_subtask

    def execute_subtask(
        self,
        provider: BaseProvider,
        system_prompt: str,
        subtask: Dict[str, Any],
        tool_runner: Callable[[str, Dict[str, Any], Dict[str, Any]], Generator[Dict[str, Any], None, Dict[str, Any]]],
        prior_evidence: List[str] | None = None,
        retry_guidance: str = "",
        enable_thinking: bool = True,
        is_interrupted_fn: Callable[[], bool] = lambda: False,
    ) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        """
        Executes a single subtask across up to max_turns_subtask rounds.
        Returns an ExecutionReport dict for CriticAgent.
        """
        task_lines = [
            f"Please complete this sub-task assigned by PlannerAgent:",
            f"**[{subtask.get('id')}] {subtask.get('title')}**",
            "",
            str(subtask.get("scope", "")),
        ]
        if prior_evidence:
            task_lines.extend([
                "",
                "Verified Tool Evidence from Previous Sub-Tasks (use these exact facts — do NOT invent missing values):",
                *[f"- {e}" for e in prior_evidence[-8:]],
            ])
        if retry_guidance:
            task_lines.extend([
                "",
                f"CriticAgent Feedback from Previous Attempt (MUST address this):",
                retry_guidance,
            ])

        history: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(task_lines)},
        ]

        tool_records: List[Dict[str, Any]] = []
        evidence_snippets: List[str] = []
        last_assistant_text = ""

        for turn in range(self.max_turns_subtask):
            if is_interrupted_fn():
                break

            yield {"type": "turn_start", "round": turn + 1}
            current_text: List[str] = []
            tool_calls: List[Dict[str, Any]] = []

            for chunk in provider.chat_stream(
                history,
                tools=TOOLS_SCHEMA,
                temperature=0.7,
                enable_thinking=enable_thinking,
            ):
                if is_interrupted_fn():
                    break
                ctype = chunk.get("type")
                if ctype == "token":
                    current_text.append(chunk.get("content", ""))
                    yield {"type": "token", "content": chunk.get("content", "")}
                elif ctype == "thinking":
                    yield {"type": "thinking", "content": chunk.get("content", "")}
                elif ctype == "tool_call":
                    tool_calls.append(chunk.get("tool_call"))
                elif ctype == "error":
                    yield {"type": "error", "error": chunk.get("error", "Unknown provider error")}
                    return {
                        "subtask_id": subtask.get("id"),
                        "last_response": last_assistant_text,
                        "tool_records": tool_records,
                        "evidence_snippets": evidence_snippets,
                        "provider_error": chunk.get("error", ""),
                    }
                elif ctype == "status":
                    yield {"type": "status", "message": chunk.get("message", "")}

            if is_interrupted_fn():
                break

            accumulated = "".join(current_text).strip()
            if accumulated:
                last_assistant_text = accumulated

            if tool_calls:
                history.append({"role": "assistant", "content": accumulated, "tool_calls": tool_calls})
                for tc in tool_calls:
                    if is_interrupted_fn():
                        break
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments", {})
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                    except Exception:
                        args = {}

                    result = yield from tool_runner(name, args, tc)
                    ok_flag = bool(result.get("ok", False))
                    if name == "run_command" and ok_flag and result.get("exit_code", 0) != 0:
                        ok_flag = False
                    tool_records.append({
                        "name": name,
                        "ok": ok_flag,
                        "args": args,
                        "error": result.get("error") or result.get("stderr") or result.get("reason") or "",
                    })
                    evidence_snippets.append(_summarize_tool_result(name, result))

                    history.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"exec_{turn}_{name}"),
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
            else:
                history.append({"role": "assistant", "content": accumulated})
                break

        return {
            "subtask_id": subtask.get("id"),
            "last_response": last_assistant_text,
            "tool_records": tool_records,
            "evidence_snippets": evidence_snippets,
            "provider_error": "",
        }
