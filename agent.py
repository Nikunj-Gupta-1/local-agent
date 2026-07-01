import os, sys, json, re, datetime, select, termios, tty
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

class ScratchpadManager:
    def __init__(self, output_dir: Path):
        self.path = output_dir / SCRATCHPAD_NAME
        self.goal = ""
        self.plan = []  # list of dicts: {"id": int, "title": str, "scope": str, "depends_on": list, "done": bool}
        self.files = set()
        self.discoveries = []
        self.notes = []
        self.user_prompts = []

    def clear(self):
        self.goal = ""
        self.plan = []
        self.files = set()
        self.discoveries = []
        self.notes = []
        self.user_prompts = []
        if self.path.exists():
            try:
                self.path.unlink()
            except Exception:
                pass

    def add_prompt(self, prompt: str):
        if prompt.strip() and prompt.strip() not in self.user_prompts:
            self.user_prompts.append(prompt.strip())
            self.write()

    def add_file(self, filepath: str):
        resolved = Path(filepath).resolve()
        workspace_roots = CFG["workspace_roots"]
        path_str = str(resolved)
        for root in workspace_roots:
            try:
                rel = resolved.relative_to(Path(root).resolve())
                path_str = str(rel)
                break
            except ValueError:
                pass
        
        # Never add scratchpad itself to the list
        if resolved.name == SCRATCHPAD_NAME:
            return

        if path_str not in self.files:
            self.files.add(path_str)
            self.write()

    def add_discovery(self, text: str):
        if text.strip() and text.strip() not in self.discoveries:
            self.discoveries.append(text.strip())
            self.write()

    def add_note(self, text: str):
        if text.strip() and text.strip() not in self.notes:
            self.notes.append(text.strip())
            self.write()

    def mark_done(self, subtask_id: int):
        for st in self.plan:
            if st["id"] == subtask_id:
                st["done"] = True
        self.write()

    def load_or_init(self, goal: str, subtasks: list = None):
        self.goal = goal
        if subtasks:
            self.plan = [
                {
                    "id": st["id"],
                    "title": st["title"],
                    "scope": st["scope"],
                    "depends_on": st.get("depends_on", []),
                    "done": False,
                }
                for st in subtasks
            ]
        else:
            self.plan = []
        self.write()

    def build_agent_view(self) -> str:
        """
        Formats a focused scratchpad for the LLM prompt.
        Hides future pending tasks so the agent focuses only on current sub-task.
        """
        lines = [
            "## Goal",
            self.goal or "(none)",
            "",
            "## User Prompts History (Session)",
        ]
        for idx, p in enumerate(self.user_prompts, 1):
            lines.append(f"{idx}. {p}")
        if not self.user_prompts:
            lines.append("_(none yet)_")

        lines.extend([
            "",
            "## Plan Progress",
        ])
        
        current_found = False
        if self.plan:
            for st in self.plan:
                if st["done"]:
                    lines.append(f"- [x] **[{st['id']}] {st['title']}** (Completed)")
                elif not current_found:
                    lines.append(f"- [/] **[{st['id']}] {st['title']}** (CURRENT FOCUS — Only implement this!) — {st['scope']}")
                    current_found = True
                else:
                    # Hide future pending tasks in prompt context
                    pass
        else:
            lines.append("_(no structured plan — single task mode)_")

        lines.extend([
            "",
            "## Files Created/Modified",
        ])
        for f in sorted(self.files):
            lines.append(f"- `{f}`")
        if not self.files:
            lines.append("_(none yet)_")

        lines.extend([
            "",
            "## Key Discoveries",
        ])
        for d in self.discoveries:
            lines.append(f"- {d}")
        if not self.discoveries:
            lines.append("_(none yet)_")

        lines.extend([
            "",
            "## Notes / Warnings",
        ])
        for n in self.notes:
            lines.append(f"- {n}")
        if not self.notes:
            lines.append("_(none yet)_")

        return "\n".join(lines)

    def write(self):
        """Write the complete plan view to the scratchpad.md file for the user."""
        lines = [
            "# Agent Scratchpad",
            "",
            "## Goal",
            "",
            self.goal or "(none)",
            "",
            "## User Prompts History",
            ""
        ]
        for idx, p in enumerate(self.user_prompts, 1):
            lines.append(f"{idx}. {p}")
        if not self.user_prompts:
            lines.append("_(none yet)_")

        lines.extend([
            "",
            "## Plan",
            ""
        ])
        for st in self.plan:
            status = "[x]" if st["done"] else "[ ]"
            lines.append(f"- {status} **[{st['id']}] {st['title']}** — {st['scope']}")
        if not self.plan:
            lines.append("_(no structured plan)_")

        lines.extend([
            "",
            "## Files Created/Modified",
            ""
        ])
        for f in sorted(self.files):
            lines.append(f"- `{f}`")
        if not self.files:
            lines.append("_(none yet)_")

        lines.extend([
            "",
            "## Key Discoveries",
            ""
        ])
        for d in self.discoveries:
            lines.append(f"- {d}")
        if not self.discoveries:
            lines.append("_(none yet)_")

        lines.extend([
            "",
            "## Notes / Warnings",
            ""
        ])
        for n in self.notes:
            lines.append(f"- {n}")
        if not self.notes:
            lines.append("_(none yet)_")

        lines.append("")
        
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines), encoding="utf-8")
        log("scratchpad_update", {"path": str(self.path)})

SCRATCHPAD = ScratchpadManager(Path(CFG["output_dir"]))

def build_system_with_scratchpad() -> str:
    """Inject current scratchpad state into the system prompt."""
    pad = SCRATCHPAD.build_agent_view()
    if not pad.strip():
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + f"\n\n---\n## Current Scratchpad State\n\n{pad}\n---"

def read_scratchpad() -> str:
    """Read the current scratchpad markdown file."""
    if SCRATCHPAD.path.exists():
        try:
            return SCRATCHPAD.path.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


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
    },
    {
        "type": "function",
        "function": {
            "name": "update_scratchpad",
            "description": "Save critical insights, decisions, variable names, and notes/reminders to your scratchpad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_discoveries": {
                        "type": "string",
                        "description": "New facts, constraints, variable names, or architecture details discovered. Leave empty if none."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Important reminders, next steps, or warning highlights for future turns. Leave empty if none."
                    }
                }
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

# ── AI Provider Configuration ─────────────────────────────────────────────────
PROVIDER = "ollama"  # "ollama" or "nvidia"
NVIDIA_API_KEY = ""

def call_nvidia_nim(messages: list, temperature: float = 1.0, tools: list = None) -> dict:
    url = f"{CFG.get('nvidia_url', 'https://integrate.api.nvidia.com/v1')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model":    CFG["model"],
        "messages": messages,
        "temperature": temperature,
        "top_p":       0.95,
        "max_tokens":  16384,
    }
    
    # If using Nemotron reasoning budget or enabling thinking
    if CFG.get("enable_thinking", False):
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        # Keep reasoning_budget strictly less than max_tokens to prevent validation issues
        payload["reasoning_budget"] = 12288

    # Format tools parameter for OpenAI-compatible endpoint
    if tools is None:
        payload["tools"] = TOOLS
    elif len(tools) > 0:
        payload["tools"] = tools

    if DEBUG >= 2:
        print(dim(f"\n[DEBUG] → NVIDIA NIM  model={CFG['model']}  messages={len(messages)}  ~{estimate_tokens(messages)} tokens"))
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=300)
        r.raise_for_status()
        res = r.json()
        choice = res["choices"][0]
        message = choice["message"]
        
        content = message.get("content", "") or ""
        thinking = message.get("reasoning_content", "") or ""
        tool_calls = message.get("tool_calls") or []
        
        return {
            "message": {
                "role": "assistant",
                "content": content,
                "thinking": thinking,
                "tool_calls": tool_calls
            }
        }
    except Exception as e:
        print(err(f"\n✗ NVIDIA NIM error: {e}"))
        if 'r' in locals() and r.text:
            print(dim(f"Response: {r.text}"))
        return {}

def call_llm(messages: list, temperature: float = 1.0, tools: list = None) -> dict:
    if PROVIDER == "nvidia":
        return call_nvidia_nim(messages, temperature, tools)
    return call_ollama(messages, temperature, tools)

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
            if result.get("ok") and "path" in result:
                SCRATCHPAD.add_file(result["path"])
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
            # Enforce manual authorization for all commands and check blocked list
            for pattern in blocked:
                if pattern in cmd:
                    return {
                        "ok": False,
                        "blocked": True,
                        "reason": f"Command contains blocked pattern: '{pattern}'",
                        "cmd": cmd,
                    }
            print(f"\n{YLW}⚠  Agent wants to run terminal command:{RST}")
            print(f"   {bold(cmd)}")
            ans = input("   Authorize this command? [y/N] ").strip().lower()
            if ans == "y":
                result = run_command(cmd, blocked, confirm, timeout, max_cmd, auto_confirm=True)
            else:
                result = {"ok": False, "cmd": cmd, "error": "User declined authorization"}
            return result

        elif name == "edit_file_lines":
            result = edit_file_lines(
                args["path"],
                args["start_line"],
                args["end_line"],
                args["new_text"],
                roots,
                create_backup=True,
            )
            if result.get("ok"):
                SCRATCHPAD.add_file(args["path"])
            return result

        elif name == "update_scratchpad":
            disc = args.get("key_discoveries", "")
            note = args.get("notes", "")
            if disc:
                SCRATCHPAD.add_discovery(disc)
            if note:
                SCRATCHPAD.add_note(note)
            return {"ok": True, "message": "Scratchpad updated successfully."}

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

def check_user_interrupt() -> bool:
    """Non-blocking check if user has pressed Tab or Escape key."""
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        return False
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        rlist, _, _ = select.select([sys.stdin], [], [], 0.0)
        if rlist:
            char = sys.stdin.read(1)
            # \t is Tab, \x1b is Escape
            if char in ("\t", "\x1b"):
                return True
    except Exception:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return False


def clean_args(args):
    """Recursively search and clean double-escaped strings in tool call arguments."""
    if isinstance(args, dict):
        return {k: clean_args(v) for k, v in args.items()}
    elif isinstance(args, list):
        return [clean_args(v) for v in args]
    elif isinstance(args, str):
        if '\\' in args and '\n' not in args:
            is_code = (
                '\\n' in args and (
                    ' ' in args or
                    '=' in args or
                    '(' in args or
                    'def ' in args or
                    'class ' in args or
                    'import ' in args
                )
            )
            is_escaped_quote = '\\"' in args or "\\'" in args
            if is_code or is_escaped_quote:
                try:
                    decoded = json.loads('"' + args + '"')
                    return decoded
                except Exception:
                    pass
        return args
    else:
        return args

# ── agent turn (with context eviction) ───────────────────────────────────────
def run_turn(user_input: str, history: list) -> list:
    history.append({"role": "user", "content": user_input})
    log("user", {"content": user_input})

    for round_idx in range(12):   # max tool rounds per turn
        # Update system prompt with the latest scratchpad state
        for msg in history:
            if msg.get("role") == "system":
                msg["content"] = build_system_with_scratchpad()
                break

        if round_idx > 0:
            if check_user_interrupt():
                print(f"\n{RED}{bold('[INTERRUPT]')}{RST} Pause requested by user (Tab/Esc pressed).")
                feedback = input(f"  Type correction to redirect, or press Enter to resume: ").strip()
                if feedback:
                    print(f"  Resuming with user correction: {info(feedback)}")
                    history.append({"role": "user", "content": f"User correction/interruption: {feedback}"})
                    log("user_interrupt", {"feedback": feedback})
                else:
                    print("  Resuming agent execution...")

        history = maybe_evict(history)
        resp    = call_llm(history)
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
                args = clean_args(args)

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
    # Give the planner awareness of what was already done this session
    scratchpad_context = read_scratchpad().strip() or "(nothing done yet — this is the first request)"

    planner_messages = [
        {"role": "system", "content": "You are a concise task planning assistant. Reply only with the requested JSON."},
        {"role": "user",   "content": PLANNER_PROMPT.format(
            request            = user_request,
            workspace_snapshot = snapshot,
            max_subtasks       = max_subtasks,
            scratchpad_context = scratchpad_context,
        )},
    ]

    print(f"\n{mag('◈  Planner:')} Analysing task scope…")
    resp = call_llm(planner_messages, temperature=0.2, tools=[])
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
- Do NOT fail the agent for approaching the sub-task differently than the title describes,
  as long as the work advances the goal.
- If the agent used tools (read files, ran commands, wrote files), treat that as evidence of work.
- Only mark satisfied=false if the agent clearly did NOTHING useful or produced a wrong result.
- If the agent explicitly asked the user a clarifying question and got an answer, that counts as progress.
- Be practical, not pedantic.

Reply with ONLY a valid JSON object (no markdown, no commentary):
{{
  "satisfied": true | false,
  "reason": "one sentence explaining your decision",
  "next_action": "what the agent should do next if not satisfied (empty string if satisfied)"
}}
"""


def _build_agent_summary(history: list, last_response: str) -> str:
    """
    Build a richer summary for the evaluator by including:
    - The last meaningful assistant text response
    - Snippets of the most recent tool results
    """
    parts = []

    # Include last text response if non-trivial
    if last_response and last_response != "(no response)" and not last_response.startswith("Agent completed actions via tools:"):
        parts.append(f"Agent response:\n{last_response[:1500]}")

    # Include recent tool call names + result snippets (last 6 tool messages)
    tool_summary_lines = []
    tool_count = 0
    for msg in reversed(history):
        if tool_count >= 6:
            break
        if msg.get("role") == "tool":
            try:
                payload = json.loads(msg["content"])
                ok_flag = payload.get("ok", True)
                # Pick a representative value to show
                snippet = ""
                for key in ("content", "stdout", "entries", "matches", "path", "error"):
                    if key in payload:
                        val = str(payload[key])
                        snippet = val[:200] + "…" if len(val) > 200 else val
                        break
                status = "✓" if ok_flag else "✗"
                tool_summary_lines.append(f"  {status} tool result: {snippet}")
                tool_count += 1
            except Exception:
                pass
        elif msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                tool_summary_lines.append(f"  → called: {fn.get('name', '?')}")

    if tool_summary_lines:
        parts.append("Recent tool activity (most recent first):\n" + "\n".join(reversed(tool_summary_lines)))

    return "\n\n".join(parts) if parts else "(agent produced no output)"


def satisfaction_check(subtask: dict, last_response: str, history: list, original_request: str = "") -> dict:
    """
    Evaluate whether the agent's last response satisfactorily completes the sub-task.
    Returns a dict with keys: satisfied (bool), reason (str), next_action (str).
    """
    loop_cfg = CFG.get("satisfaction_loop", {})
    if not loop_cfg.get("enabled", True):
        return {"satisfied": True, "reason": "Satisfaction loop disabled.", "next_action": ""}

    eval_temp    = loop_cfg.get("evaluator_temperature", 0.1)
    agent_summary = _build_agent_summary(history, last_response)

    eval_messages = [
        {"role": "system", "content": "You are a practical completion evaluator. Reply only with the requested JSON."},
        {"role": "user",   "content": EVALUATOR_PROMPT.format(
            original_request = original_request or "(not specified)",
            title            = subtask.get("title", "Unknown"),
            scope            = subtask.get("scope", ""),
            agent_summary    = agent_summary[:3000],
        )},
    ]

    resp = call_llm(eval_messages, temperature=eval_temp, tools=[])
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

# ── run a single sub-task with satisfaction loop ──────────────────────────────
def run_subtask(subtask: dict, base_history: list, original_request: str = "") -> tuple[str, list]:
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

    # Build a fresh context: system prompt + scratchpad only.
    # run_turn will append the user message; do NOT pre-add it here.
    history = [
        {"role": "system", "content": build_system_with_scratchpad()},
    ]

    last_response = ""

    for attempt in range(1, max_retries + 2):  # +1 so we always get at least one attempt
        if attempt == 1:
            prompt = f"Please complete this sub-task:\n**{title}**\n\n{scope}"
        else:
            prompt = (
                f"The previous attempt was incomplete.\n"
                f"Reason: {last_response[:300]}\n\n"
                f"Please continue and finish the sub-task:\n**{title}**\n\n{scope}"
            )

        history = run_turn(prompt, history)

        # Extract last meaningful assistant response.
        # Gemma often returns empty content on its final message after tool
        # calls — skip those and fall back to a tool-call summary.
        last_response = ""
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("content", "").strip():
                last_response = msg["content"].strip()
                break

        if not last_response:
            # Synthesise a summary from the most recent tool calls
            tool_names = []
            for msg in reversed(history[-10:]):
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {})
                        tool_names.append(fn.get("name", "unknown"))
            last_response = (
                f"Agent completed actions via tools: {', '.join(tool_names)}"
                if tool_names else "(no response)"
            )

        # Evaluate satisfaction
        eval_result = satisfaction_check(subtask, last_response, history, original_request)
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

def refiner_pass(user_input: str) -> str:
    """
    Refine the user's prompt by expanding it into a detailed system specification
    using the model, allowing the user to accept, edit, or reject the refinement.
    """
    refiner_cfg = CFG.get("prompt_refiner", {})
    if not refiner_cfg.get("enabled", True):
        return user_input

    # Skip for simple CLI commands or exit statements
    if user_input.lower() in ("exit", "quit", "bye") or len(user_input) < 10:
        return user_input

    print(f"\n{mag('◈  Refiner:')} Refining your prompt for better planning...")

    refiner_prompt = f"""\
You are an expert prompt engineer and software requirements specifier.
The user wants to run an autonomous AI coding agent with the following request:
"{user_input}"

Your task is to rewrite, expand, and refine this prompt into a highly detailed, structured, and comprehensive specification.
Specifically:
1. Elaborate on the core goals and requirements.
2. Outline specific inputs, outputs, data formats, and edge cases to handle.
3. List assumptions, architectural preferences, and testing expectations.
4. Keep the request clear, actionable, and structured using markdown headers.

Return ONLY the refined prompt (as a detailed markdown document). Do NOT include any introductory or concluding remarks (like "Here is the refined prompt..."). Start directly with the markdown content.
"""

    refiner_messages = [
        {"role": "system", "content": "You are a software requirement refining assistant. Output only the refined markdown specification."},
        {"role": "user", "content": refiner_prompt}
    ]

    resp = call_llm(refiner_messages, temperature=0.3, tools=[])
    if not resp:
        return user_input

    refined = resp.get("message", {}).get("content", "") or ""
    refined = refined.strip()

    if not refined or len(refined) < len(user_input) * 0.8:
        return user_input

    print(f"\n{bold('── Refined Prompt Suggestion ──')}")
    print(refined)
    print(f"{bold('───────────────────────────────')}")

    print(f"\n❓ Accept this refined prompt?")
    print(f"   [y] Accept (recommended)")
    print(f"   [n] Reject (use original)")
    print(f"   [e] Edit the refined prompt")
    
    ans = input("  Your choice [Y/n/e]: ").strip().lower()
    if ans == "n":
        print(f"  Using original prompt.")
        return user_input
    elif ans == "e":
        temp_path = Path(CFG["output_dir"]) / "refined_prompt.md"
        temp_path.write_text(refined, encoding="utf-8")
        print(f"\n📝 Saved refined prompt to: {info(temp_path)}")
        input("  Please open and edit the file in your preferred editor. Press Enter here when saved... ")
        try:
            edited = temp_path.read_text(encoding="utf-8").strip()
            if edited:
                temp_path.unlink(missing_ok=True)
                return edited
        except Exception as e:
            print(err(f"  Error reading file: {e}. Using un-edited refined prompt."))
        temp_path.unlink(missing_ok=True)
        return refined
    else:
        print(f"  Using refined prompt.")
        return refined


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    global PROVIDER, NVIDIA_API_KEY
    Path(CFG["output_dir"]).mkdir(parents=True, exist_ok=True)

    print(f"\n{bold('╔══════════════════════════════════════════════════════╗')}")
    print(f"{bold('║             Select AI Model Provider                 ║')}")
    print(f"{bold('╚══════════════════════════════════════════════════════╝')}")
    print("  [1] Local Ollama (default)")
    print(f"      Model  : {dim(CFG.get('model', 'gemma4-e4b-64k:latest'))}")
    print("  [2] NVIDIA NIM")
    print(f"      Model  : {dim('nvidia/nemotron-3-ultra-550b-a55b')}")
    print("")
    
    try:
        choice = input(bold("Select provider [1-2] (default: 1): ")).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nBye!")
        sys.exit(0)

    if choice == "2":
        PROVIDER = "nvidia"
        CFG["model"] = "nvidia/nemotron-3-ultra-550b-a55b"
        CFG["nvidia_url"] = "https://integrate.api.nvidia.com/v1"
        CFG["context_window"] = 16384
        CFG["enable_thinking"] = True
        
        env_key = os.environ.get("NVIDIA_API_KEY")
        cfg_key = CFG.get("nvidia_api_key")
        
        if env_key:
            NVIDIA_API_KEY = env_key
            print(f"  Using NVIDIA API key from environment variable: {info('NVIDIA_API_KEY')}")
        elif cfg_key:
            NVIDIA_API_KEY = cfg_key
            print(f"  Using NVIDIA API key from {info('config.yaml')}")
        else:
            print(warn("\n  NVIDIA API key not found in environment or config."))
            try:
                key_input = input(bold("  Paste your NVIDIA API Key: ")).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nBye!")
                sys.exit(0)
            if not key_input:
                print(err("  Error: NVIDIA API Key is required for NIM."))
                sys.exit(1)
            NVIDIA_API_KEY = key_input
    else:
        PROVIDER = "ollama"

    scope_enabled = CFG.get("scope_assessment", {}).get("enabled", True)
    loop_enabled  = CFG.get("satisfaction_loop", {}).get("enabled", True)

    print(f"""
{BLD}╔══════════════════════════════════════════════════════╗
║    Local Agent Ready  ·  {PROVIDER.upper()} Mode          ║
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

    # Clear scratchpad at startup
    SCRATCHPAD.clear()

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

        # ── Step 0: Prompt Refiner Pass ──────────────────────────────────────
        refined_input = refiner_pass(user_input)
        if refined_input != user_input:
            user_input = refined_input

        # Record prompt to the persistent scratchpad history
        SCRATCHPAD.add_prompt(user_input)

        # ── Step 1: Planner Pass ─────────────────────────────────────────────
        subtasks = planner_pass(user_input)

        if not subtasks:
            # No plan (simple task or planner disabled) — run as single turn
            SCRATCHPAD.load_or_init(user_input, None)
            simple_subtask = {"id": 1, "title": user_input, "scope": user_input, "depends_on": []}
            run_subtask(simple_subtask, [], original_request=user_input)
            alert_user("Agent done", "Task complete.")
            continue

        # ── Step 2: Initialise scratchpad ────────────────────────────────────
        SCRATCHPAD.load_or_init(user_input, subtasks)
        print(f"\n{dim(f'Plan saved to: {SCRATCHPAD.path}')}")

        # ── Step 3: Execute sub-tasks with satisfaction loop ─────────────────
        total   = len(subtasks)
        history = []   # shared history across sub-tasks (scratchpad handles continuity)

        for idx, subtask in enumerate(subtasks, 1):
            print(f"\n{dim('─'*55)}")
            print(f"{mag(f'  Sub-task {idx}/{total}')}: {bold(subtask['title'])}")
            print(dim('─'*55))

            _, history = run_subtask(subtask, history, original_request=user_input)
            SCRATCHPAD.mark_done(subtask["id"])

        # ── Step 4: Done ─────────────────────────────────────────────────────
        print(f"\n{ok('✓')} {bold('All sub-tasks complete.')}")
        alert_user("Agent done", f"All {total} sub-tasks complete. Check output folder.")
        log("task_complete", {"subtasks_total": total})


if __name__ == "__main__":
    main()
