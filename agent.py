#!/usr/bin/env python3
"""
agent.py — Local Ollama Filesystem + Shell Agent
─────────────────────────────────────────────────
Usage:
    python agent.py

Requires:
    pip install requests pyyaml

Ollama must be running:
    ollama serve   (or open the Ollama.app on Mac)
"""

import os, sys, json, re, datetime
import yaml, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tools.files  import list_dir, find_similar_files, read_file, read_file_lines, stat_file
from tools.shell  import run_command
from tools.writer import write_file
from tools.editing import edit_file_lines
from tools.notify import alert_user

# ── config ────────────────────────────────────────────────────────────────────
CFG_PATH = Path(__file__).parent / "config.yaml"

def load_config():
    with open(CFG_PATH) as f:
        cfg = yaml.safe_load(f)
    cfg["workspace_roots"] = [
        str(Path(os.path.expanduser(r)).resolve())
        for r in cfg.get("workspace_roots", [])
    ]
    cfg["output_dir"] = str(Path(os.path.expanduser(cfg["output_dir"])).resolve())
    cfg["log_dir"]    = str(Path(os.path.expanduser(cfg["log_dir"])).resolve())
    return cfg

CFG   = load_config()
DEBUG = int(CFG.get("debug_level", 1))

# ── terminal colours ──────────────────────────────────────────────────────────
RST  = "\033[0m";  CYAN = "\033[96m"; YLW = "\033[93m"
GRN  = "\033[92m"; RED  = "\033[91m"; GRY = "\033[90m"; BLD = "\033[1m"
MAG  = "\033[95m"
def dim(t):    return f"{GRY}{t}{RST}"
def info(t):   return f"{CYAN}{t}{RST}"
def warn(t):   return f"{YLW}{t}{RST}"
def ok(t):     return f"{GRN}{t}{RST}"
def err(t):    return f"{RED}{t}{RST}"
def bold(t):   return f"{BLD}{t}{RST}"
def mag(t):    return f"{MAG}{t}{RST}"

# ── session log ───────────────────────────────────────────────────────────────
def start_log():
    d = Path(CFG["log_dir"]); d.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return d / f"session_{ts}.jsonl"

LOG = start_log()

def log(event, data):
    entry = {"ts": datetime.datetime.now().isoformat(), "event": event, **data}
    with open(LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ── system prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.txt").read_text()

# ── scratchpad ────────────────────────────────────────────────────────────────
SCRATCHPAD_NAME = "scratchpad.md"

def scratchpad_path() -> Path:
    return Path(CFG["output_dir"]) / SCRATCHPAD_NAME

def read_scratchpad() -> str:
    p = scratchpad_path()
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""

def write_scratchpad(content: str):
    p = scratchpad_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    log("scratchpad_update", {"path": str(p), "chars": len(content)})

def build_system_with_scratchpad() -> str:
    """Inject current scratchpad state into the system prompt."""
    pad = read_scratchpad()
    if not pad.strip():
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + f"\n\n---\n## Current Scratchpad State\n\n{pad}\n---"

# ── tool schema (Ollama native tool-call format) ──────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and folders inside an allowed directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_files",
            "description": "Search for files whose name contains keywords from the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords to search for"},
                    "root":  {"type": "string", "description": "Directory to search inside"},
                },
                "required": ["query", "root"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full text content of a file. "
                "ONLY use for small files (<20KB). "
                "For larger files, use read_file_lines instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or ~/... file path"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_lines",
            "description": (
                "Read a specific inclusive line range from a file (1-indexed). "
                "PREFERRED over read_file for large files. "
                "Always use stat_file first to learn total_lines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":       {"type": "string",  "description": "Absolute or ~/... file path"},
                    "start_line": {"type": "integer", "description": "First line to read (1-indexed)"},
                    "end_line":   {"type": "integer", "description": "Last line to read (inclusive)"},
                },
                "required": ["path", "start_line", "end_line"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stat_file",
            "description": (
                "Get file metadata (size, modified date, total lines) without reading content. "
                "Always use this before read_file to check if the file is large."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return its stdout, stderr, and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file in the output folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Filename only, no path"},
                    "content":  {"type": "string", "description": "Full text content to write"},
                    "append":   {"type": "boolean", "description": "Append instead of overwrite"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Pause and ask the user a clarification question before continuing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask"},
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file_lines",
            "description": "Edit an existing text file by replacing a line range. Creates a backup before writing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~/... path to the file"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "1-indexed starting line number"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "1-indexed ending line number (inclusive)"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Replacement text for that line range"
                    }
                },
                "required": ["path", "start_line", "end_line", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "alert_user",
            "description": "Send a macOS notification to the user for status updates, completion alerts, or when user attention is needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short notification title"
                    },
                    "message": {
                        "type": "string",
                        "description": "Short notification body"
                    }
                },
                "required": ["title", "message"]
            }
        }
    }
]

# ── context management ────────────────────────────────────────────────────────

def estimate_tokens(messages: list) -> int:
    """
    Rough token estimate: ~3 characters per token.
    Used to decide when to trigger context eviction.
    """
    total_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
    return total_chars // 3


EVICT_PLACEHOLDER = "[Content evicted to save context space. Use read_file or read_file_lines again if needed.]"
EVICT_TOOLS       = {"read_file", "read_file_lines", "run_command", "list_dir", "find_similar_files"}
EVICT_MIN_CHARS   = 800   # only evict tool outputs larger than this


def evict_old_tool_outputs(messages: list, context_window: int, target_pct: float = 0.70) -> list:
    """
    Walk older messages from the front and replace large tool outputs with a
    lightweight placeholder until estimated token usage drops below target_pct.

    Returns a new list (original is not mutated).
    """
    target_tokens = int(context_window * target_pct)
    msgs = list(messages)

    # Don't touch: system prompt (index 0), last 6 messages (active context)
    evict_window = msgs[1:-6] if len(msgs) > 7 else []

    for i, msg in enumerate(msgs):
        if estimate_tokens(msgs) <= target_tokens:
            break
        # Only evict tool result messages that are large
        if msg.get("role") != "tool":
            continue
        content_str = msg.get("content", "")
        if len(content_str) <= EVICT_MIN_CHARS:
            continue
        # Check if this is an evictable tool type
        try:
            payload = json.loads(content_str)
            if not isinstance(payload, dict):
                continue
        except Exception:
            continue
        # Replace with placeholder
        msgs[i] = {
            "role":    "tool",
            "content": json.dumps({"ok": True, "content": EVICT_PLACEHOLDER}, ensure_ascii=False),
        }
        if DEBUG >= 1:
            print(dim(f"   [ctx] evicted tool message at index {i}"))
        log("context_eviction", {"index": i, "original_chars": len(content_str)})

    return msgs


def maybe_evict(messages: list) -> list:
    """
    Check if we are approaching the context limit and evict if needed.
    Trigger: estimated tokens > 80% of context_window.
    """
    context_window = CFG.get("context_window", 16384)
    threshold      = int(context_window * 0.80)
    if estimate_tokens(messages) > threshold:
        if DEBUG >= 1:
            print(warn(f"\n[ctx] History at >{80}% of context window — running eviction…"))
        messages = evict_old_tool_outputs(messages, context_window, target_pct=0.65)
    return messages

# ── Ollama API ────────────────────────────────────────────────────────────────
def call_ollama(messages: list, temperature: float = 1.0, tools: list = None) -> dict:
    url = f"{CFG['ollama_url']}/api/chat"
    payload = {
        "model":    CFG["model"],
        "messages": messages,
        "tools":    tools if tools is not None else TOOLS,
        "stream":   False,
        "think":    CFG.get("enable_thinking", False),
        "options": {
            "num_ctx":     CFG.get("context_window", 16384),
            "temperature": temperature,
            "top_k":       64,
            "top_p":       0.95,
        },
    }
    if DEBUG >= 2:
        print(dim(f"\n[DEBUG] → Ollama  model={CFG['model']}  messages={len(messages)}  ~{estimate_tokens(messages)} tokens"))
    try:
        r = requests.post(url, json=payload, timeout=300)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        print(err("\n✗ Cannot reach Ollama. Make sure it is running:  ollama serve"))
        sys.exit(1)
    except Exception as e:
        print(err(f"\n✗ Ollama error: {e}"))
        return {}

# ── tool dispatch ─────────────────────────────────────────────────────────────
def dispatch(name, args):
    roots   = CFG["workspace_roots"]
    max_f   = CFG.get("max_file_bytes", 32000)
    max_cmd = CFG.get("max_command_output_chars", 4000)
    timeout = CFG.get("command_timeout", 30)
    blocked = CFG.get("blocked_commands", [])
    confirm = CFG.get("confirm_commands", [])

    try:
        if name == "list_dir":
            return list_dir(args["path"], roots)

        elif name == "find_similar_files":
            return find_similar_files(args["query"], args["root"], roots)

        elif name == "read_file":
            return read_file(args["path"], roots, max_bytes=max_f)

        elif name == "read_file_lines":
            return read_file_lines(
                args["path"], roots,
                int(args["start_line"]),
                int(args["end_line"]),
            )

        elif name == "stat_file":
            return stat_file(args["path"], roots)

        elif name == "write_file":
            result = write_file(
                args["filename"],
                args["content"],
                CFG["output_dir"],
                append=args.get("append", False),
            )
            # If the agent wrote the scratchpad, sync it so the next call picks it up
            if args["filename"] == SCRATCHPAD_NAME:
                log("scratchpad_update", {"via": "agent_write_file"})
            return result

        elif name == "alert_user":
            return alert_user(
                args["title"],
                args["message"],
            )

        elif name == "ask_user":
            q = args.get("question", "")
            print(f"\n❓ Agent asks: {q}")
            answer = input("  Your answer: ").strip()
            return {"ok": True, "user_answer": answer}

        elif name == "run_command":
            cmd = args["cmd"]
            result = run_command(cmd, blocked, confirm, timeout, max_cmd, auto_confirm=False)
            if result.get("needs_confirm"):
                print(f"\n⚠ Needs confirmation: {cmd}")
                ans = input("  Run it? [y/N] ").strip().lower()
                if ans == "y":
                    result = run_command(cmd, blocked, confirm, timeout, max_cmd, auto_confirm=True)
                else:
                    result = {"ok": False, "cmd": cmd, "error": "User declined"}
            return result

        elif name == "edit_file_lines":
            return edit_file_lines(
                args["path"],
                args["start_line"],
                args["end_line"],
                args["new_text"],
                roots,
                create_backup=True,
            )

        else:
            return {"ok": False, "error": f"Unknown tool: {name}"}

    except PermissionError as e:
        return {
            "ok": False,
            "error": str(e),
            "error_type": "PermissionError",
            "allowed_roots": roots,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }

# ── agent turn (with context eviction) ───────────────────────────────────────
def run_turn(user_input: str, history: list) -> list:
    history.append({"role": "user", "content": user_input})
    log("user", {"content": user_input})

    for _ in range(12):   # max tool rounds per turn
        history = maybe_evict(history)
        resp    = call_ollama(history)
        if not resp:
            break

        msg      = resp.get("message", {})
        content  = msg.get("content", "") or ""
        thinking = msg.get("thinking", "") or ""
        calls    = msg.get("tool_calls") or []

        # ── show thinking if debug >= 2 ──────────────────────────────────────
        if DEBUG >= 2 and thinking.strip():
            print(f"\n{GRY}── 🧠 thinking {'─'*35}{RST}")
            for line in thinking.strip().splitlines():
                print(dim("  " + line))
            print(dim("─" * 50))

        # ── native tool call from Ollama ─────────────────────────────────────
        if calls:
            history.append({"role": "assistant", "content": content,
                            "tool_calls": calls})

            for tc in calls:
                fn   = tc.get("function", {})
                name = fn.get("name", "")
                raw  = fn.get("arguments", {})
                args = json.loads(raw) if isinstance(raw, str) else raw

                if DEBUG >= 1:
                    display_args = {k: v for k, v in args.items() if k != "content"}
                    print(f"\n{YLW}⚙  Tool:{RST} {bold(name)}")
                    for k, v in display_args.items():
                        preview = str(v)[:120] + "…" if len(str(v)) > 120 else str(v)
                        print(f"   {dim(k+':'):<22} {preview}")

                result = dispatch(name, args)
                log("tool", {"tool": name, "args": args, "result": result})

                if DEBUG >= 1:
                    status = ok("ok") if result.get("ok") else err("error")
                    print(f"   {dim('result:'):<22} [{status}]", end="")
                    for key in ("stdout", "content", "path", "entries", "matches", "error"):
                        if key in result:
                            val = str(result[key])
                            snippet = val[:160] + "…" if len(val) > 160 else val
                            print(f"  {snippet}")
                            break
                    else:
                        print()

                history.append({
                    "role":    "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                })

        else:
            # No tool calls — final answer
            history.append({"role": "assistant", "content": content})
            log("assistant", {"content": content})
            print(f"\n{GRN}●{RST} {bold('Agent:')}")
            print(content.strip())
            break

    return history

# ── planner pass ──────────────────────────────────────────────────────────────
PLANNER_PROMPT = """\
You are a planning assistant. Do NOT execute anything yet.

The user has made the following request:
{request}

Here is the top-level workspace structure:
{workspace_snapshot}

Your job:
1. Estimate the complexity of this task (small / medium / large).
2. Decompose the task into an ordered list of focused sub-tasks.
   - Each sub-task must be completable in a single focused LLM session using at most 50% of the context window.
   - Each sub-task should be atomic, self-contained, and clearly scoped.
   - Aim for 1–{max_subtasks} sub-tasks. Do not over-decompose simple tasks.
3. Return ONLY a valid JSON object in this exact format (no markdown, no commentary):

{{
  "complexity": "small|medium|large",
  "reasoning": "one sentence explaining your complexity estimate",
  "subtasks": [
    {{"id": 1, "title": "...", "scope": "...", "depends_on": []}},
    {{"id": 2, "title": "...", "scope": "...", "depends_on": [1]}},
    ...
  ]
}}
"""

def snapshot_workspace() -> str:
    """Return a brief top-level listing of the primary workspace root."""
    root = CFG["workspace_roots"][0] if CFG["workspace_roots"] else "."
    try:
        result = list_dir(root, CFG["workspace_roots"])
        if result.get("ok"):
            entries = result.get("entries", [])
            lines = [f"  {'[DIR] ' if e['type']=='dir' else '      '}{e['name']}" for e in entries[:30]]
            return f"{root}/\n" + "\n".join(lines)
    except Exception:
        pass
    return "(could not snapshot workspace)"


def planner_pass(user_request: str) -> list | None:
    """
    Run a dedicated planning pass.
    Returns an ordered list of sub-task dicts, or None if planning is disabled/skipped.
    """
    scope_cfg = CFG.get("scope_assessment", {})
    if not scope_cfg.get("enabled", True):
        return None

    max_subtasks = scope_cfg.get("max_subtasks", 20)
    snapshot     = snapshot_workspace()

    planner_messages = [
        {"role": "system", "content": "You are a concise task planning assistant. Reply only with the requested JSON."},
        {"role": "user",   "content": PLANNER_PROMPT.format(
            request           = user_request,
            workspace_snapshot= snapshot,
            max_subtasks      = max_subtasks,
        )},
    ]

    print(f"\n{mag('◈  Planner:')} Analysing task scope…")
    resp = call_ollama(planner_messages, temperature=0.2, tools=[])
    if not resp:
        return None

    raw = resp.get("message", {}).get("content", "") or ""

    # Extract JSON — model may wrap in code fences
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        print(warn("  [planner] Could not parse plan — proceeding as single task."))
        return None

    try:
        plan = json.loads(json_match.group())
    except json.JSONDecodeError:
        print(warn("  [planner] Invalid JSON in plan — proceeding as single task."))
        return None

    subtasks   = plan.get("subtasks", [])
    complexity = plan.get("complexity", "unknown")
    reasoning  = plan.get("reasoning", "")

    print(f"\n{mag('◈  Plan')} ({bold(complexity)} task — {reasoning})\n")
    for st in subtasks:
        dep_str  = f"  depends: {st['depends_on']}" if st.get("depends_on") else ""
        st_label = dim(f"[{st['id']}]")
        print(f"  {st_label} {bold(st['title'])}{dep_str}")
        print(f"       {dim(st['scope'])}")

    log("planner_pass", {"complexity": complexity, "subtasks": subtasks})
    return subtasks

# ── satisfaction evaluator ────────────────────────────────────────────────────
EVALUATOR_PROMPT = """\
You are a strict completion evaluator. Be brief and objective.

The original sub-task was:
Title: {title}
Scope: {scope}

The agent's last response was:
---
{last_response}
---

Is this sub-task complete and correct?

Reply with ONLY a valid JSON object (no markdown, no commentary):
{{
  "satisfied": true | false,
  "reason": "one sentence explaining your decision",
  "next_action": "what the agent should do next to complete this (leave empty string if satisfied)"
}}
"""

def satisfaction_check(subtask: dict, last_response: str) -> dict:
    """
    Evaluate whether the agent's last response satisfactorily completes the sub-task.
    Returns a dict with keys: satisfied (bool), reason (str), next_action (str).
    """
    loop_cfg = CFG.get("satisfaction_loop", {})
    if not loop_cfg.get("enabled", True):
        return {"satisfied": True, "reason": "Satisfaction loop disabled.", "next_action": ""}

    eval_temp = loop_cfg.get("evaluator_temperature", 0.1)

    eval_messages = [
        {"role": "system", "content": "You are a concise completion evaluator. Reply only with the requested JSON."},
        {"role": "user",   "content": EVALUATOR_PROMPT.format(
            title         = subtask.get("title", "Unknown"),
            scope         = subtask.get("scope", ""),
            last_response = last_response[:3000],   # cap to avoid evaluator context issues
        )},
    ]

    resp = call_ollama(eval_messages, temperature=eval_temp, tools=[])
    if not resp:
        return {"satisfied": True, "reason": "Evaluator call failed — assuming done.", "next_action": ""}

    raw = resp.get("message", {}).get("content", "") or ""
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        return {"satisfied": True, "reason": "Could not parse evaluator response — assuming done.", "next_action": ""}

    try:
        result = json.loads(json_match.group())
        return result
    except json.JSONDecodeError:
        return {"satisfied": True, "reason": "Invalid evaluator JSON — assuming done.", "next_action": ""}

# ── scratchpad initializer ────────────────────────────────────────────────────
def init_scratchpad(user_request: str, subtasks: list | None):
    """Write the initial scratchpad with the overall goal and plan."""
    lines = [
        "# Agent Scratchpad\n",
        f"## Goal\n\n{user_request}\n",
    ]
    if subtasks:
        lines.append("## Plan\n")
        for st in subtasks:
            lines.append(f"- [ ] **[{st['id']}] {st['title']}** — {st['scope']}")
        lines.append("")
    lines.append("## Key Discoveries\n\n_(none yet)_\n")
    lines.append("## Current Sub-task\n\n_(starting)_\n")
    lines.append("## Notes\n\n_(none yet)_\n")

    write_scratchpad("\n".join(lines))

def mark_subtask_done(subtask: dict):
    """Update scratchpad to mark a sub-task as complete."""
    pad = read_scratchpad()
    marker = f"- [ ] **[{subtask['id']}]"
    done   = f"- [x] **[{subtask['id']}]"
    updated = pad.replace(marker, done, 1)
    write_scratchpad(updated)

# ── run a single sub-task with satisfaction loop ──────────────────────────────
def run_subtask(subtask: dict, base_history: list) -> tuple[str, list]:
    """
    Execute a single sub-task with a retry loop.
    Returns (last_response, updated_history).
    """
    loop_cfg    = CFG.get("satisfaction_loop", {})
    max_retries = loop_cfg.get("max_retries", 4)
    title       = subtask.get("title", "Sub-task")
    scope       = subtask.get("scope", "")

    print(f"\n{mag('◈  Sub-task:')} {bold(title)}")
    print(f"   {dim(scope)}\n")

    # Build a fresh context for this sub-task (system + scratchpad + task description)
    history = [
        {"role": "system", "content": build_system_with_scratchpad()},
        {"role": "user",   "content": f"Current sub-task:\n**{title}**\n\n{scope}"},
    ]

    last_response = ""

    for attempt in range(1, max_retries + 2):  # +1 so we always get at least one attempt
        history = run_turn(
            f"Please complete this sub-task: {title}\n{scope}" if attempt == 1
            else f"The previous attempt was incomplete. {last_response[:200]}… Please continue from where it left off and finish: {title}",
            history if attempt > 1 else history[:-1],   # first pass: history already has the user msg from init
        )

        # Extract last assistant response
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                last_response = msg.get("content", "")
                break

        # Evaluate satisfaction
        eval_result = satisfaction_check(subtask, last_response)
        satisfied   = eval_result.get("satisfied", True)
        reason      = eval_result.get("reason", "")
        next_action = eval_result.get("next_action", "")

        if satisfied:
            print(f"\n  {ok('✓')} {dim('Evaluator:')} {reason}")
            log("satisfaction_check", {"subtask_id": subtask.get("id"), "attempt": attempt,
                                       "satisfied": True, "reason": reason})
            break
        else:
            print(f"\n  {warn('↻')} {dim('Evaluator:')} {reason}")
            if next_action:
                print(f"  {dim('Next action:')} {next_action}")
            log("satisfaction_check", {"subtask_id": subtask.get("id"), "attempt": attempt,
                                       "satisfied": False, "reason": reason, "next_action": next_action})
            if attempt > max_retries:
                print(warn(f"\n  ⚠ Max retries ({max_retries}) reached for sub-task [{subtask.get('id')}]. Moving on."))
                alert_user("Agent warning", f"Sub-task {subtask.get('id')} hit max retries: {title}")
                break
            # Inject evaluator feedback for the next attempt
            last_response = next_action or reason

    return last_response, history

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    Path(CFG["output_dir"]).mkdir(parents=True, exist_ok=True)

    scope_enabled = CFG.get("scope_assessment", {}).get("enabled", True)
    loop_enabled  = CFG.get("satisfaction_loop", {}).get("enabled", True)

    print(f"""
{BLD}╔══════════════════════════════════════════════════════╗
║    Local Ollama Agent  ·  ready                      ║
╚══════════════════════════════════════════════════════╝{RST}
  Model   : {info(CFG['model'])}
  Context : {info(str(CFG.get('context_window',16384)) + ' tokens')}
  Thinking: {info(str(CFG.get('enable_thinking', False)))}
  Roots   : {info(', '.join(CFG['workspace_roots']))}
  Output  : {info(CFG['output_dir'])}
  Log     : {dim(str(LOG))}
  Debug   : {info(str(DEBUG))}  (0=quiet  1=tools  2=full+thinking)
  Planner : {ok('on') if scope_enabled else warn('off')}
  Loop    : {ok('on') if loop_enabled else warn('off')}

{dim('Type your request and press Enter.  "exit" to quit.')}
""")

    if DEBUG >= 2:
        print(dim("── system prompt " + "─"*35))
        for line in SYSTEM_PROMPT.strip().splitlines():
            print(dim("  " + line))
        print(dim("─" * 52 + "\n"))

    while True:
        try:
            user_input = input(f"\n{BLD}You:{RST} ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Bye!")
            break

        # ── Step 1: Planner Pass ─────────────────────────────────────────────
        subtasks = planner_pass(user_input)

        if not subtasks:
            # No plan (simple task or planner disabled) — run as single turn
            init_scratchpad(user_input, None)
            simple_subtask = {"id": 1, "title": user_input, "scope": user_input, "depends_on": []}
            run_subtask(simple_subtask, [])
            alert_user("Agent done", "Task complete.")
            continue

        # ── Step 2: Initialise scratchpad ────────────────────────────────────
        init_scratchpad(user_input, subtasks)
        print(f"\n{dim(f'Plan saved to: {scratchpad_path()}')}")

        # ── Step 3: Execute sub-tasks with satisfaction loop ─────────────────
        total   = len(subtasks)
        history = []   # shared history across sub-tasks (scratchpad handles continuity)

        for idx, subtask in enumerate(subtasks, 1):
            print(f"\n{dim('─'*55)}")
            print(f"{mag(f'  Sub-task {idx}/{total}')}: {bold(subtask['title'])}")
            print(dim('─'*55))

            _, history = run_subtask(subtask, history)
            mark_subtask_done(subtask)

        # ── Step 4: Done ─────────────────────────────────────────────────────
        print(f"\n{ok('✓')} {bold('All sub-tasks complete.')}")
        alert_user("Agent done", f"All {total} sub-tasks complete. Check output folder.")
        log("task_complete", {"subtasks_total": total})


if __name__ == "__main__":
    main()
