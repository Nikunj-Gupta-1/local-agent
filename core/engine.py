"""
core/engine.py
──────────────
Decoupled Agent Execution Engine. Emits structured streaming events
for GUI consumers without blocking terminal dependencies.
"""

import os
import sys
import json
import time
import queue
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Generator

from core.providers import get_provider
from core.providers.base import BaseProvider
from core.tools_schema import TOOLS_SCHEMA
from core.scratchpad import ScratchpadManager
from core.planner import run_planner_pass
from core.evaluator import check_satisfaction
from core.classifier import PromptClassifier
from core.memory.store import MemoryStore
from core.memory.hook import get_memory_context
from core.memory.indexer import harvest_session_memory

from tools.files import list_dir, find_similar_files, read_file, read_file_lines, stat_file
from tools.shell import run_command
from tools.writer import write_file
from tools.editing import edit_file_lines
from tools.notify import alert_user
from tools.memory import recall_memory, set_memory_store


class AgentEngine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider_name = config.get("provider", "ollama")
        self.provider: BaseProvider = get_provider(self.provider_name, config)

        self.workspace_roots = [
            str(Path(os.path.expanduser(r)).resolve())
            for r in config.get("workspace_roots", [os.getcwd()])
        ]
        self.output_dir = Path(os.path.expanduser(config.get("output_dir", "./output"))).resolve()
        self.log_dir = Path(os.path.expanduser(config.get("log_dir", "./logs/sessions"))).resolve()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.scratchpad = ScratchpadManager(self.output_dir, self.workspace_roots)
        self.memory_store = MemoryStore(ollama_url=config.get("ollama_url", "http://127.0.0.1:11434"))
        set_memory_store(self.memory_store)

        self.safety_mode = config.get("safety_mode", "safe")  # 'safe', 'auto', 'strict'
        self.is_interrupted = False

        # System prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "system.txt"
        self.base_system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "You are an autonomous coding assistant."

        # Input response queue for interactive approvals and ask_user
        self.approval_queues: Dict[str, queue.Queue] = {}

    def set_safety_mode(self, mode: str):
        if mode in ("safe", "auto", "strict"):
            self.safety_mode = mode

    def set_provider(self, provider_name: str, config: Dict[str, Any]):
        self.config.update(config)
        self.provider_name = provider_name
        self.provider = get_provider(provider_name, self.config)

    def set_workspace_root(self, root_path: str):
        resolved = str(Path(os.path.expanduser(root_path)).resolve())
        self.workspace_roots = [resolved]
        self.scratchpad.workspace_roots = self.workspace_roots

    def interrupt(self):
        """Signal the engine to pause/stop processing immediately."""
        self.is_interrupted = True

    def submit_user_response(self, action_id: str, response_data: Dict[str, Any]):
        """Delivers user approval / input from the GUI to a waiting tool action."""
        if action_id in self.approval_queues:
            self.approval_queues[action_id].put(response_data)

    def _snapshot_workspace(self) -> str:
        root = self.workspace_roots[0] if self.workspace_roots else "."
        try:
            res = list_dir(root, self.workspace_roots)
            if res.get("ok"):
                lines = [f"  {'[DIR] ' if e['type']=='dir' else '      '}{e['name']}" for e in res.get("entries", [])[:25]]
                return f"{root}/\n" + "\n".join(lines)
        except Exception:
            pass
        return "(could not snapshot workspace)"

    def _build_full_system_prompt(self, memory_context: str = "") -> str:
        pad = self.scratchpad.build_agent_view()
        parts = [self.base_system_prompt]
        if memory_context:
            parts.append(f"\n---\n{memory_context}\n---")
        if pad.strip():
            parts.append(f"\n---\n## Current Scratchpad State\n\n{pad}\n---")
        return "\n\n".join(parts)

    def _dispatch_tool(self, name: str, args: Dict[str, Any], action_id: str) -> Dict[str, Any]:
        roots = self.workspace_roots
        max_f = self.config.get("max_file_bytes", 65536)
        max_cmd = self.config.get("max_command_output_chars", 4000)
        timeout = self.config.get("command_timeout", 30)
        blocked = self.config.get("blocked_commands", ["rm -rf", "mkfs", "dd if="])

        if name == "list_dir":
            return list_dir(args.get("path", "."), roots)
        elif name == "find_similar_files":
            return find_similar_files(args.get("query", ""), args.get("root", roots[0]), roots)
        elif name == "read_file":
            return read_file(args.get("path", ""), roots, max_bytes=max_f)
        elif name == "read_file_lines":
            return read_file_lines(args.get("path", ""), roots, int(args.get("start_line", 1)), int(args.get("end_line", 100)))
        elif name == "stat_file":
            return stat_file(args.get("path", ""), roots)
        elif name == "write_file":
            res = write_file(args.get("filename", ""), args.get("content", ""), str(self.output_dir), append=args.get("append", False))
            if res.get("ok") and "path" in res:
                self.scratchpad.add_file(res["path"])
            return res
        elif name == "edit_file_lines":
            res = edit_file_lines(args.get("path", ""), int(args.get("start_line", 1)), int(args.get("end_line", 1)), args.get("new_text", ""), roots)
            if res.get("ok"):
                self.scratchpad.add_file(args.get("path", ""))
            return res
        elif name == "alert_user":
            return alert_user(args.get("title", "Agent Notification"), args.get("message", ""))
        elif name == "update_scratchpad":
            disc = args.get("key_discoveries", "")
            note = args.get("notes", "")
            if disc:
                self.scratchpad.add_discovery(disc)
            if note:
                self.scratchpad.add_note(note)
            return {"ok": True, "message": "Scratchpad updated."}
        elif name == "recall_memory":
            return recall_memory(args.get("query", ""), project_path=roots[0] if roots else "")
        elif name == "run_command":
            cmd = args.get("cmd", "")
            for pattern in blocked:
                if pattern in cmd:
                    return {"ok": False, "blocked": True, "reason": f"Command blocked by safety filter: {pattern}", "cmd": cmd}
            return run_command(cmd, blocked, [], timeout=timeout, max_output_chars=max_cmd, auto_confirm=True)
        return {"ok": False, "error": f"Unknown tool: {name}"}

    def execute_stream(self, user_prompt: str, session_id: str = "") -> Generator[Dict[str, Any], None, None]:
        """
        Executes an agent run and yields structured JSON events for real-time UI rendering.
        """
        self.is_interrupted = False
        project_root = self.workspace_roots[0] if self.workspace_roots else os.getcwd()
        yield {"type": "run_start", "prompt": user_prompt, "project_root": project_root, "timestamp": datetime.datetime.now().isoformat()}

        self.scratchpad.add_prompt(user_prompt)

        # 1. Recall Long-Term Memory
        memory_ctx, recalled_items = get_memory_context(self.memory_store, user_prompt, project_root, top_k=3)
        if recalled_items:
            yield {"type": "memory_recalled", "items": recalled_items}

        # 2. Classify Intent: Direct Response vs Multi-Step Plan
        classifier_mode = self.config.get("prompt_classifier", {}).get("mode", "auto")
        classifier = PromptClassifier(mode=classifier_mode)
        route, reason = classifier.classify(user_prompt, provider=self.provider)
        yield {"type": "route_selected", "route": route, "reason": reason}

        # ── Fast Path: Direct Single-Response Execution ──
        if route == "DIRECT":
            direct_history = [
                {"role": "system", "content": self._build_full_system_prompt(memory_ctx)},
                {"role": "user", "content": user_prompt},
            ]

            for turn in range(5):
                if self.is_interrupted:
                    yield {"type": "interrupted", "message": "Execution halted by user."}
                    break

                current_text = []
                current_thinking = []
                tool_calls = []

                for chunk in self.provider.chat_stream(
                    direct_history,
                    tools=TOOLS_SCHEMA,
                    temperature=0.7,
                    enable_thinking=self.config.get("enable_thinking", True),
                ):
                    if self.is_interrupted:
                        break

                    chunk_type = chunk.get("type")
                    if chunk_type == "token":
                        current_text.append(chunk.get("content", ""))
                        yield {"type": "token", "content": chunk.get("content", "")}
                    elif chunk_type == "thinking":
                        current_thinking.append(chunk.get("content", ""))
                        yield {"type": "thinking", "content": chunk.get("content", "")}
                    elif chunk_type == "tool_call":
                        tool_calls.append(chunk.get("tool_call"))
                    elif chunk_type == "error":
                        yield {"type": "error", "error": chunk.get("error", "Unknown error")}
                        return
                    elif chunk_type == "status":
                        yield {"type": "status", "message": chunk.get("message", "")}

                if self.is_interrupted:
                    break

                accumulated_text = "".join(current_text).strip()
                if tool_calls:
                    direct_history.append({"role": "assistant", "content": accumulated_text, "tool_calls": tool_calls})
                    for tc in tool_calls:
                        if self.is_interrupted:
                            break
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        raw_args = fn.get("arguments", {})
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        action_id = f"action_{int(time.time()*1000)}_{name}"

                        needs_approval = False
                        if name == "ask_user":
                            needs_approval = True
                            yield {"type": "ask_user", "action_id": action_id, "question": args.get("question", "")}
                        elif self.safety_mode == "strict":
                            needs_approval = True
                            yield {"type": "tool_approval_required", "action_id": action_id, "name": name, "args": args}
                        elif self.safety_mode == "safe" and name in ("run_command", "write_file", "edit_file_lines"):
                            needs_approval = True
                            yield {"type": "tool_approval_required", "action_id": action_id, "name": name, "args": args}
                        else:
                            yield {"type": "tool_executing", "name": name, "args": args}

                        if needs_approval:
                            q = queue.Queue()
                            self.approval_queues[action_id] = q
                            resp = q.get()
                            del self.approval_queues[action_id]
                            if not resp.get("approved", True):
                                result = {"ok": False, "error": "Action rejected by user in GUI."}
                                yield {"type": "tool_result", "name": name, "result": result}
                                direct_history.append({"role": "tool", "tool_call_id": tc.get("id", action_id), "name": name, "content": json.dumps(result)})
                                continue
                            if name == "ask_user" and "answer" in resp:
                                result = {"ok": True, "user_answer": resp["answer"]}
                                yield {"type": "tool_result", "name": name, "result": result}
                                direct_history.append({"role": "tool", "tool_call_id": tc.get("id", action_id), "name": name, "content": json.dumps(result)})
                                continue

                        result = self._dispatch_tool(name, args, action_id)
                        yield {"type": "tool_result", "name": name, "result": result}
                        direct_history.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", action_id),
                            "name": name,
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                else:
                    break

            yield {"type": "complete", "timestamp": datetime.datetime.now().isoformat()}
            return

        # ── Autonomous Planning Path ──
        subtasks = None
        if self.config.get("scope_assessment", {}).get("enabled", True):
            yield {"type": "planner_start"}
            snapshot = self._snapshot_workspace()
            plan_res = run_planner_pass(
                self.provider,
                user_prompt,
                snapshot,
                self.scratchpad.path.read_text(encoding="utf-8") if self.scratchpad.path.exists() else "",
            )
            if plan_res and plan_res.get("subtasks"):
                subtasks = plan_res["subtasks"]
                yield {
                    "type": "plan_created",
                    "complexity": plan_res.get("complexity", "medium"),
                    "reasoning": plan_res.get("reasoning", ""),
                    "subtasks": subtasks,
                }

        if not subtasks:
            subtasks = [{"id": 1, "title": user_prompt, "scope": user_prompt, "depends_on": []}]
            yield {"type": "plan_created", "complexity": "small", "reasoning": "Single atomic task", "subtasks": subtasks}

        self.scratchpad.load_or_init(user_prompt, subtasks)

        # Execute Plan Subtasks
        overall_solution = ""
        for subtask in subtasks:
            if self.is_interrupted:
                yield {"type": "interrupted", "message": "Execution halted by user."}
                break

            yield {"type": "subtask_start", "subtask": subtask}
            subtask_history = [
                {"role": "system", "content": self._build_full_system_prompt(memory_ctx)},
                {"role": "user", "content": f"Please complete this sub-task:\n**{subtask['title']}**\n\n{subtask['scope']}"},
            ]

            tool_records = []
            last_assistant_text = ""

            for turn in range(10):
                if self.is_interrupted:
                    break

                current_text = []
                current_thinking = []
                tool_calls = []

                yield {"type": "turn_start", "round": turn + 1}

                for chunk in self.provider.chat_stream(
                    subtask_history,
                    tools=TOOLS_SCHEMA,
                    temperature=0.7,
                    enable_thinking=self.config.get("enable_thinking", True),
                ):
                    if self.is_interrupted:
                        break

                    chunk_type = chunk.get("type")
                    if chunk_type == "token":
                        current_text.append(chunk.get("content", ""))
                        yield {"type": "token", "content": chunk.get("content", "")}
                    elif chunk_type == "thinking":
                        current_thinking.append(chunk.get("content", ""))
                        yield {"type": "thinking", "content": chunk.get("content", "")}
                    elif chunk_type == "tool_call":
                        tool_calls.append(chunk.get("tool_call"))
                    elif chunk_type == "error":
                        yield {"type": "error", "error": chunk.get("error", "Unknown error")}
                        return
                    elif chunk_type == "status":
                        yield {"type": "status", "message": chunk.get("message", "")}

                if self.is_interrupted:
                    break

                accumulated_text = "".join(current_text).strip()
                if accumulated_text:
                    last_assistant_text = accumulated_text
                    overall_solution = accumulated_text

                if tool_calls:
                    subtask_history.append({"role": "assistant", "content": accumulated_text, "tool_calls": tool_calls})
                    for tc in tool_calls:
                        if self.is_interrupted:
                            break

                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        raw_args = fn.get("arguments", {})
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        action_id = f"action_{int(time.time()*1000)}_{name}"

                        needs_approval = False
                        if name == "ask_user":
                            needs_approval = True
                            yield {"type": "ask_user", "action_id": action_id, "question": args.get("question", "")}
                        elif self.safety_mode == "strict":
                            needs_approval = True
                            yield {"type": "tool_approval_required", "action_id": action_id, "name": name, "args": args}
                        elif self.safety_mode == "safe" and name in ("run_command", "write_file", "edit_file_lines"):
                            needs_approval = True
                            yield {"type": "tool_approval_required", "action_id": action_id, "name": name, "args": args}
                        else:
                            yield {"type": "tool_executing", "name": name, "args": args}

                        if needs_approval:
                            q = queue.Queue()
                            self.approval_queues[action_id] = q
                            resp = q.get()
                            del self.approval_queues[action_id]

                            if not resp.get("approved", True):
                                result = {"ok": False, "error": "Action rejected by user in GUI."}
                                yield {"type": "tool_result", "name": name, "result": result}
                                subtask_history.append({"role": "tool", "tool_call_id": tc.get("id", action_id), "name": name, "content": json.dumps(result)})
                                continue

                            if name == "ask_user" and "answer" in resp:
                                result = {"ok": True, "user_answer": resp["answer"]}
                                yield {"type": "tool_result", "name": name, "result": result}
                                subtask_history.append({"role": "tool", "tool_call_id": tc.get("id", action_id), "name": name, "content": json.dumps(result)})
                                continue

                        result = self._dispatch_tool(name, args, action_id)
                        tool_records.append({"name": name, "ok": result.get("ok", False)})
                        yield {"type": "tool_result", "name": name, "result": result}

                        subtask_history.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", action_id),
                            "name": name,
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                else:
                    subtask_history.append({"role": "assistant", "content": accumulated_text})
                    break

            # Evaluate Satisfaction
            eval_res = check_satisfaction(self.provider, subtask, last_assistant_text, tool_records, user_prompt)
            self.scratchpad.mark_done(subtask["id"])
            yield {
                "type": "subtask_evaluated",
                "subtask_id": subtask["id"],
                "satisfied": eval_res.get("satisfied", True),
                "reason": eval_res.get("reason", "Subtask completed."),
            }

        # Session Complete & Harvest Memory RAG
        harvest_session_memory(
            memory_store=self.memory_store,
            project_path=project_root,
            session_id=session_id or f"sess_{int(time.time())}",
            goal=user_prompt,
            discoveries=self.scratchpad.discoveries,
            notes=self.scratchpad.notes,
            solution_summary=overall_solution,
        )

        yield {
            "type": "complete",
            "scratchpad": self.scratchpad.to_dict(),
            "timestamp": datetime.datetime.now().isoformat(),
        }
