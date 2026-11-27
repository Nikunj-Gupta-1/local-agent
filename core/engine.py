"""
core/engine.py
──────────────
Decoupled Multi-Agent Execution Engine. Emits structured streaming events
for Desktop GUI, Web UI, and programmatic consumers without blocking.

Coordinates three specialized collaborating agents over CollaborationBus:
  - PlannerAgent  : Workspace discovery, dependency DAG planning, and dynamic replanning
  - ExecutorAgent : Tool-using execution loop with grounded evidence tracking
  - CriticAgent   : Independent verification using read-only tools & structured feedback
"""

import os
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
from core.classifier import PromptClassifier
from core.memory.store import MemoryStore
from core.memory.hook import get_memory_context
from core.memory.indexer import harvest_session_memory
from core.agents import CollaborationBus, PlannerAgent, ExecutorAgent, CriticAgent

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
        self.memory_store = MemoryStore(
            db_path=config.get("memory_db_path"),
            ollama_url=config.get("ollama_url", "http://127.0.0.1:11434"),
            auto_seed=config.get("seed_knowledge_base"),
        )
        set_memory_store(self.memory_store)

        self.safety_mode = config.get("safety_mode", "safe")  # 'safe', 'auto', 'strict'
        self.is_interrupted = False
        self.redirect_feedback: Optional[str] = None

        # Specialized multi-agent collaborators
        max_sub = int(config.get("scope_assessment", {}).get("max_subtasks", 12))
        eval_temp = float(config.get("satisfaction_loop", {}).get("evaluator_temperature", 0.1))
        self.planner_agent = PlannerAgent(max_subtasks=max_sub)
        self.executor_agent = ExecutorAgent()
        self.critic_agent = CriticAgent(temperature=eval_temp)
        self.bus = CollaborationBus()

        # System prompt template
        prompt_path = Path(__file__).parent.parent / "prompts" / "system.txt"
        self.base_system_prompt = (
            prompt_path.read_text(encoding="utf-8")
            if prompt_path.exists()
            else "You are a local assistant with access to:\n{workspace_roots_list}"
        )

        # Input response queue for interactive approvals, plan review, and ask_user
        self.approval_queues: Dict[str, queue.Queue] = {}
        self._action_seq = 0

    def _next_action_id(self, name: str) -> str:
        self._action_seq += 1
        return f"action_{int(time.time() * 1000)}_{self._action_seq}_{name}"

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

    def redirect(self, feedback: str):
        """Supply mid-run redirection instructions that trigger dynamic replanning."""
        fb = (feedback or "").strip()
        if fb:
            self.redirect_feedback = fb

    def submit_user_response(self, action_id: str, response_data: Dict[str, Any]):
        """Delivers user approval / input from the UI to a waiting HITL queue."""
        q = self.approval_queues.get(action_id)
        if q is not None:
            q.put(response_data)

    def _snapshot_workspace(self) -> str:
        root = self.workspace_roots[0] if self.workspace_roots else "."
        try:
            res = list_dir(root, self.workspace_roots)
            if res.get("ok"):
                lines = [
                    f"  {'[DIR] ' if e['type'] == 'dir' else '      '}{e['name']}"
                    for e in res.get("entries", [])[:25]
                ]
                return f"{root}/\n" + "\n".join(lines)
        except Exception:
            pass
        return "(could not snapshot workspace)"

    def _build_full_system_prompt(self, memory_context: str = "") -> str:
        roots_block = "\n".join(f"- {r}" for r in self.workspace_roots) or "- ."
        base_prompt = self.base_system_prompt.replace("{workspace_roots_list}", roots_block)
        pad = self.scratchpad.build_agent_view()
        parts = [base_prompt]
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

        try:
            if name == "list_dir":
                return list_dir(args.get("path", "."), roots)
            elif name == "find_similar_files":
                return find_similar_files(args.get("query", ""), args.get("root", roots[0]), roots)
            elif name == "read_file":
                return read_file(args.get("path", ""), roots, max_bytes=max_f)
            elif name == "read_file_lines":
                return read_file_lines(
                    args.get("path", ""),
                    roots,
                    int(args.get("start_line", 1)),
                    int(args.get("end_line", 100)),
                )
            elif name == "stat_file":
                return stat_file(args.get("path", ""), roots)
            elif name == "write_file":
                res = write_file(
                    args.get("filename", ""),
                    args.get("content", ""),
                    str(self.output_dir),
                    append=args.get("append", False),
                )
                if res.get("ok") and "path" in res:
                    self.scratchpad.add_file(res["path"])
                return res
            elif name == "edit_file_lines":
                res = edit_file_lines(
                    args.get("path", ""),
                    int(args.get("start_line", 1)),
                    int(args.get("end_line", 1)),
                    args.get("new_text", ""),
                    roots,
                )
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
                        return {
                            "ok": False,
                            "blocked": True,
                            "reason": f"Command blocked by safety filter: {pattern}",
                            "cmd": cmd,
                        }
                return run_command(cmd, blocked, [], timeout=timeout, max_output_chars=max_cmd, auto_confirm=True)
            return {"ok": False, "error": f"Unknown tool: {name}"}
        except PermissionError as exc:
            return {
                "ok": False,
                "error": str(exc),
                "error_type": "PermissionError",
                "allowed_roots": roots,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

    def _await_hitl_response(self, event_payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        """Register queue BEFORE yielding so fast/synchronous consumers never deadlock."""
        action_id = event_payload["action_id"]
        q: queue.Queue = queue.Queue()
        self.approval_queues[action_id] = q
        try:
            yield event_payload
            return q.get()
        finally:
            self.approval_queues.pop(action_id, None)

    def _run_tool_with_hitl(
        self,
        name: str,
        args: Dict[str, Any],
        tc: Dict[str, Any],
        readonly_for_subagent: bool = False,
    ) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        """Enforce safety policy, run tool, yield events, and return tool result dict."""
        action_id = self._next_action_id(name)

        needs_approval = False
        if name == "ask_user":
            needs_approval = True
            ev = {"type": "ask_user", "action_id": action_id, "question": args.get("question", "")}
        elif self.safety_mode == "strict":
            needs_approval = True
            ev = {"type": "tool_approval_required", "action_id": action_id, "name": name, "args": args}
        elif (
            not readonly_for_subagent
            and self.safety_mode == "safe"
            and name in ("run_command", "write_file", "edit_file_lines")
        ):
            needs_approval = True
            ev = {"type": "tool_approval_required", "action_id": action_id, "name": name, "args": args}
        else:
            ev = {"type": "tool_executing", "name": name, "args": args}

        if needs_approval:
            resp = yield from self._await_hitl_response(ev)
            if not resp.get("approved", True):
                feedback = str(resp.get("feedback", "")).strip()
                msg = f"Action rejected by user: {feedback}" if feedback else "Action rejected by user in UI."
                if feedback:
                    self.redirect(feedback)
                result = {"ok": False, "error": msg}
                yield {"type": "tool_result", "name": name, "result": result}
                return result
            if name == "ask_user" and "answer" in resp:
                result = {"ok": True, "user_answer": resp["answer"]}
                yield {"type": "tool_result", "name": name, "result": result}
                return result
        else:
            yield ev

        result = self._dispatch_tool(name, args, action_id)
        yield {"type": "tool_result", "name": name, "result": result}
        return result

    def _emit_bus_msg(
        self,
        sender: str,
        recipient: str,
        message_type: str,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        msg = self.bus.send(sender, recipient, message_type, summary, payload)
        return msg.to_event()

    def execute_stream(self, user_prompt: str, session_id: str = "") -> Generator[Dict[str, Any], None, None]:
        """Executes a user prompt via DIRECT fast path or multi-agent PLAN orchestration."""
        self.is_interrupted = False
        self.redirect_feedback = None
        self.bus = CollaborationBus()

        project_root = self.workspace_roots[0] if self.workspace_roots else os.getcwd()
        yield {
            "type": "run_start",
            "prompt": user_prompt,
            "project_root": project_root,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        self.scratchpad.add_prompt(user_prompt)

        # 1. Recall Long-Term Memory (RAG)
        memory_ctx, recalled_items = get_memory_context(self.memory_store, user_prompt, project_root, top_k=3)
        if recalled_items:
            yield {"type": "memory_recalled", "items": recalled_items}

        # 2. Classify Intent: Direct Response vs Multi-Agent Plan
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

            for _ in range(self.executor_agent.max_turns_direct):
                if self.is_interrupted:
                    yield {"type": "interrupted", "message": "Execution halted by user."}
                    break

                current_text = []
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
                        try:
                            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                        except Exception:
                            args = {}
                        result = yield from self._run_tool_with_hitl(name, args, tc)
                        direct_history.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", self._next_action_id(name)),
                            "name": name,
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                else:
                    break

            yield {"type": "complete", "timestamp": datetime.datetime.now().isoformat()}
            return

        # ── Multi-Agent Collaborative Planning & Execution Path ──
        plan_res = None
        snapshot = self._snapshot_workspace()
        scratch_txt = self.scratchpad.path.read_text(encoding="utf-8") if self.scratchpad.path.exists() else ""

        if self.config.get("scope_assessment", {}).get("enabled", True):
            yield {"type": "planner_start"}
            plan_res = yield from self.planner_agent.plan_stream(
                provider=self.provider,
                user_request=user_prompt,
                workspace_snapshot=snapshot,
                scratchpad_context=scratch_txt,
                memory_context=memory_ctx,
                tool_runner=lambda n, a, tc: self._run_tool_with_hitl(n, a, tc, readonly_for_subagent=True),
                enable_discovery_tools=bool(self.config.get("planner_discovery_tools", True)),
            )

        if not plan_res or not plan_res.get("subtasks"):
            plan_res = {
                "complexity": "small",
                "reasoning": "Single atomic task fallback",
                "subtasks": [{"id": 1, "title": user_prompt, "scope": user_prompt, "depends_on": []}],
            }

        subtasks: List[Dict[str, Any]] = plan_res["subtasks"]
        yield {
            "type": "plan_created",
            "complexity": plan_res.get("complexity", "medium"),
            "reasoning": plan_res.get("reasoning", ""),
            "subtasks": subtasks,
        }
        yield self._emit_bus_msg(
            "PlannerAgent",
            "Human",
            "plan_proposal",
            f"Proposed {len(subtasks)}-step plan ({plan_res.get('complexity', 'medium')}): {plan_res.get('reasoning', '')}",
            {"subtasks": subtasks},
        )

        # Pre-Execution HITL Plan Approval Gate (Safe / Strict modes when enabled)
        plan_approval_enabled = self.config.get("plan_approval", self.safety_mode in ("safe", "strict"))
        if plan_approval_enabled and self.safety_mode in ("safe", "strict"):
            plan_action_id = self._next_action_id("plan_approval")
            resp = yield from self._await_hitl_response({
                "type": "plan_approval_required",
                "action_id": plan_action_id,
                "complexity": plan_res.get("complexity", "medium"),
                "reasoning": plan_res.get("reasoning", ""),
                "subtasks": subtasks,
            })
            if not resp.get("approved", True):
                feedback = str(resp.get("feedback", "")).strip()
                if feedback:
                    revised = self.planner_agent.replan(
                        provider=self.provider,
                        user_request=user_prompt,
                        workspace_snapshot=snapshot,
                        completed_subtasks=[],
                        trigger_context="User requested plan modification prior to execution.",
                        feedback=feedback,
                        bus_log=self.bus.format_recent_log(),
                        scratchpad_context=self.scratchpad.build_agent_view(),
                        next_id=1,
                    )
                    if revised and revised.get("subtasks"):
                        subtasks = revised["subtasks"]
                        yield {
                            "type": "plan_updated",
                            "reason": f"Adapted to user feedback: {feedback}",
                            "subtasks": subtasks,
                        }
                else:
                    yield {"type": "interrupted", "message": "Plan cancelled by user before execution."}
                    yield {"type": "complete", "scratchpad": self.scratchpad.to_dict(), "timestamp": datetime.datetime.now().isoformat()}
                    return
            else:
                if isinstance(resp.get("subtasks"), list) and resp["subtasks"]:
                    subtasks = resp["subtasks"]
                    yield {"type": "plan_updated", "reason": "User edited plan steps.", "subtasks": subtasks}
                elif resp.get("feedback"):
                    fb = str(resp["feedback"]).strip()
                    revised = self.planner_agent.replan(
                        provider=self.provider,
                        user_request=user_prompt,
                        workspace_snapshot=snapshot,
                        completed_subtasks=[],
                        trigger_context="User added refinement instructions.",
                        feedback=fb,
                        bus_log=self.bus.format_recent_log(),
                        scratchpad_context=self.scratchpad.build_agent_view(),
                        next_id=1,
                    )
                    if revised and revised.get("subtasks"):
                        subtasks = revised["subtasks"]
                        yield {"type": "plan_updated", "reason": f"Refined per user input: {fb}", "subtasks": subtasks}

        self.scratchpad.load_or_init(user_prompt, subtasks)

        # Dependency-Aware Adaptive Execution Loop
        task_map: Dict[int, Dict[str, Any]] = {int(st["id"]): dict(st) for st in subtasks}
        completed_ids: set[int] = set()
        failed_ids: set[int] = set()
        overall_solution = ""
        max_subtask_retries = min(2, int(self.config.get("satisfaction_loop", {}).get("max_retries", 2)))
        eval_enabled = self.config.get("satisfaction_loop", {}).get("enabled", True)
        max_replans = 2
        replan_count = 0

        while len(completed_ids) + len(failed_ids) < len(task_map):
            if self.is_interrupted:
                yield {"type": "interrupted", "message": "Execution halted by user."}
                break

            # Dynamic replanning if user issued mid-run redirect feedback
            if self.redirect_feedback and replan_count < max_replans:
                fb = self.redirect_feedback
                self.redirect_feedback = None
                replan_count += 1
                next_id = max(task_map.keys(), default=0) + 1
                yield self._emit_bus_msg("Human", "PlannerAgent", "replan_request", fb)
                revised = self.planner_agent.replan(
                    provider=self.provider,
                    user_request=user_prompt,
                    workspace_snapshot=self._snapshot_workspace(),
                    completed_subtasks=[task_map[i] for i in sorted(completed_ids)],
                    trigger_context="User requested mid-run redirection.",
                    feedback=fb,
                    bus_log=self.bus.format_recent_log(),
                    scratchpad_context=self.scratchpad.build_agent_view(),
                    next_id=next_id,
                )
                if revised and revised.get("subtasks"):
                    new_sts = revised["subtasks"]
                    task_map = {cid: task_map[cid] for cid in completed_ids}
                    for st in new_sts:
                        task_map[int(st["id"])] = dict(st)
                    self.scratchpad.replace_remaining_plan(completed_ids, new_sts)
                    yield {"type": "plan_updated", "reason": f"Redirected: {fb}", "subtasks": list(task_map.values())}
                    continue

            # Pick next runnable subtask whose depends_on are all in completed_ids
            pending = [
                st for sid, st in task_map.items()
                if sid not in completed_ids and sid not in failed_ids
            ]
            runnable = [
                st for st in pending
                if all(int(dep) in completed_ids for dep in st.get("depends_on", []))
            ]

            if not runnable:
                # Blocked by failed dependency or cyclic/unknown dependency ID
                if failed_ids and replan_count < max_replans:
                    replan_count += 1
                    next_id = max(task_map.keys(), default=0) + 1
                    yield self._emit_bus_msg(
                        "ExecutorAgent",
                        "PlannerAgent",
                        "replan_request",
                        f"Remaining subtasks blocked by failed dependencies {sorted(failed_ids)}.",
                    )
                    revised = self.planner_agent.replan(
                        provider=self.provider,
                        user_request=user_prompt,
                        workspace_snapshot=self._snapshot_workspace(),
                        completed_subtasks=[task_map[i] for i in sorted(completed_ids)],
                        trigger_context=f"Subtasks {sorted(failed_ids)} failed, blocking remaining dependencies.",
                        feedback="Work around failed steps or produce an alternative path.",
                        bus_log=self.bus.format_recent_log(),
                        scratchpad_context=self.scratchpad.build_agent_view(),
                        next_id=next_id,
                    )
                    if revised and revised.get("subtasks"):
                        new_sts = revised["subtasks"]
                        task_map = {cid: task_map[cid] for cid in completed_ids}
                        for st in new_sts:
                            task_map[int(st["id"])] = dict(st)
                        self.scratchpad.replace_remaining_plan(completed_ids, new_sts)
                        yield {"type": "plan_updated", "reason": "Replanned around blocked dependency.", "subtasks": list(task_map.values())}
                        continue
                for st in pending:
                    self.scratchpad.mark_failed(int(st["id"]))
                    failed_ids.add(int(st["id"]))
                break

            subtask = sorted(runnable, key=lambda s: int(s["id"]))[0]
            sid = int(subtask["id"])
            yield {"type": "subtask_start", "subtask": subtask}
            yield self._emit_bus_msg(
                "PlannerAgent",
                "ExecutorAgent",
                "task_handoff",
                f"Execute [{sid}] {subtask['title']}",
                {"subtask_id": sid, "depends_on": subtask.get("depends_on", [])},
            )

            retry_guidance = ""
            attempts = 1 + (max_subtask_retries if eval_enabled else 0)
            succeeded = False
            replanned_this_step = False

            for attempt in range(1, attempts + 1):
                if self.is_interrupted:
                    break

                report = yield from self.executor_agent.execute_subtask(
                    provider=self.provider,
                    system_prompt=self._build_full_system_prompt(memory_ctx),
                    subtask=subtask,
                    tool_runner=lambda n, a, tc: self._run_tool_with_hitl(n, a, tc, readonly_for_subagent=False),
                    prior_evidence=self.scratchpad.evidence,
                    retry_guidance=retry_guidance,
                    enable_thinking=self.config.get("enable_thinking", True),
                    is_interrupted_fn=lambda: self.is_interrupted,
                )

                if report.get("provider_error"):
                    return

                if report.get("last_response"):
                    overall_solution = report["last_response"]
                if report.get("evidence_snippets"):
                    self.scratchpad.add_evidence(report["evidence_snippets"])

                if self.is_interrupted:
                    break

                if not eval_enabled:
                    succeeded = True
                    break

                yield self._emit_bus_msg(
                    "ExecutorAgent",
                    "CriticAgent",
                    "execution_report",
                    f"Completed attempt {attempt} for [{sid}] with {len(report.get('tool_records', []))} tool calls.",
                )

                verdict = yield from self.critic_agent.evaluate_stream(
                    provider=self.provider,
                    subtask=subtask,
                    report=report,
                    original_request=user_prompt,
                    tool_runner=lambda n, a, tc: self._run_tool_with_hitl(n, a, tc, readonly_for_subagent=True),
                )

                satisfied = bool(verdict.get("satisfied", True))
                reason_txt = verdict.get("reason", "Subtask evaluated.")
                next_act = verdict.get("next_action", "")
                needs_replan = bool(verdict.get("needs_replan", False))

                yield {
                    "type": "subtask_evaluated",
                    "subtask_id": sid,
                    "attempt": attempt,
                    "satisfied": satisfied,
                    "reason": reason_txt,
                    "next_action": next_act,
                    "needs_replan": needs_replan,
                }

                if satisfied:
                    succeeded = True
                    break

                if needs_replan or attempt >= attempts:
                    if replan_count < max_replans:
                        replan_count += 1
                        next_id = max(task_map.keys(), default=0) + 1
                        yield self._emit_bus_msg(
                            "CriticAgent",
                            "PlannerAgent",
                            "replan_request",
                            f"[{sid}] failed verification: {reason_txt} | {next_act}",
                        )
                        revised = self.planner_agent.replan(
                            provider=self.provider,
                            user_request=user_prompt,
                            workspace_snapshot=self._snapshot_workspace(),
                            completed_subtasks=[task_map[i] for i in sorted(completed_ids)],
                            trigger_context=f"Subtask [{sid}] '{subtask['title']}' failed: {reason_txt}",
                            feedback=next_act or reason_txt,
                            bus_log=self.bus.format_recent_log(),
                            scratchpad_context=self.scratchpad.build_agent_view(),
                            next_id=next_id,
                        )
                        if revised and revised.get("subtasks"):
                            new_sts = revised["subtasks"]
                            task_map = {cid: task_map[cid] for cid in completed_ids}
                            for st in new_sts:
                                task_map[int(st["id"])] = dict(st)
                            self.scratchpad.replace_remaining_plan(completed_ids, new_sts)
                            yield {
                                "type": "plan_updated",
                                "reason": f"CriticAgent triggered replan: {reason_txt}",
                                "subtasks": list(task_map.values()),
                            }
                            replanned_this_step = True
                            break
                    break

                # Targeted retry with CriticAgent's feedback
                yield self._emit_bus_msg(
                    "CriticAgent",
                    "ExecutorAgent",
                    "retry_guidance",
                    next_act or reason_txt,
                )
                retry_guidance = f"{reason_txt}\nNext action: {next_act}"

            if succeeded:
                self.scratchpad.mark_done(sid)
                completed_ids.add(sid)
            elif not replanned_this_step:
                self.scratchpad.mark_failed(sid)
                failed_ids.add(sid)

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
            "agent_messages": [m.to_dict() for m in self.bus.messages],
            "timestamp": datetime.datetime.now().isoformat(),
        }
