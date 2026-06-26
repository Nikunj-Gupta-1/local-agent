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
from tools.files  import list_dir, find_similar_files, read_file, stat_file
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
def dim(t):    return f"{GRY}{t}{RST}"
def info(t):   return f"{CYAN}{t}{RST}"
def warn(t):   return f"{YLW}{t}{RST}"
def ok(t):     return f"{GRN}{t}{RST}"
def err(t):    return f"{RED}{t}{RST}"
def bold(t):   return f"{BLD}{t}{RST}"

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
            "description": "Read the text content of a file.",
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
            "name": "stat_file",
            "description": "Get file metadata (size, modified date) without reading content.",
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

# ── Ollama API ────────────────────────────────────────────────────────────────
def call_ollama(messages):
    url = f"{CFG['ollama_url']}/api/chat"
    payload = {
        "model":    CFG["model"],
        "messages": messages,
        "tools":    TOOLS,
        "stream":   False,
        "think":    CFG.get("enable_thinking", False),
        "options": {
            "num_ctx":     CFG.get("context_window", 16384),
            "temperature": 1.0,
            "top_k":       64,
            "top_p":       0.95,
        },
    }
    if DEBUG >= 2:
        print(dim(f"\n[DEBUG] → Ollama  model={CFG['model']}  messages={len(messages)}"))
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

        elif name == "stat_file":
            return stat_file(args["path"], roots)

        elif name == "write_file":
            return write_file(
                args["filename"],
                args["content"],
                CFG["output_dir"],
                append=args.get("append", False),
            )

        elif name == "alert_user":
            return alert_user(
                args["title"],
                args["message"],
            )

        elif name == "ask_user":
            q = args.get("question", "")
            print(f"\\n❓ Agent asks: {q}")
            answer = input("  Your answer: ").strip()
            return {"ok": True, "user_answer": answer}

        elif name == "run_command":
            cmd = args["cmd"]
            result = run_command(cmd, blocked, confirm, timeout, max_cmd, auto_confirm=False)
            if result.get("needs_confirm"):
                print(f"\\n⚠ Needs confirmation: {cmd}")
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
# ── agent turn ────────────────────────────────────────────────────────────────
def run_turn(user_input, history):
    history.append({"role": "user", "content": user_input})
    log("user", {"content": user_input})

    for _ in range(12):   # max tool rounds per turn
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
            # Ollama may return multiple tool calls; process each
            history.append({"role": "assistant", "content": content,
                            "tool_calls": calls})

            for tc in calls:
                fn   = tc.get("function", {})
                name = fn.get("name", "")
                raw  = fn.get("arguments", {})
                # arguments may arrive as a string or already-parsed dict
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

                # Feed result back using Ollama's tool-result message format
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

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    Path(CFG["output_dir"]).mkdir(parents=True, exist_ok=True)

    print(f"""
{BLD}╔══════════════════════════════════════════════╗
║    Local Ollama Agent  ·  ready              ║
╚══════════════════════════════════════════════╝{RST}
  Model   : {info(CFG['model'])}
  Context : {info(str(CFG.get('context_window',16384)) + ' tokens')}
  Thinking: {info(str(CFG.get('enable_thinking', False)))}
  Roots   : {info(', '.join(CFG['workspace_roots']))}
  Output  : {info(CFG['output_dir'])}
  Log     : {dim(str(LOG))}
  Debug   : {info(str(DEBUG))}  (0=quiet  1=tools  2=full+thinking)

{dim('Type your request and press Enter.  "exit" to quit.')}
""")

    if DEBUG >= 2:
        print(dim("── system prompt " + "─"*35))
        for line in SYSTEM_PROMPT.strip().splitlines():
            print(dim("  " + line))
        print(dim("─" * 52 + "\n"))

    history = [{"role": "system", "content": SYSTEM_PROMPT}]

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

        run_turn(user_input, history)

if __name__ == "__main__":
    main()
