# Local Agent (Ollama & NVIDIA NIM)

A lightweight Python agent that connects your local filesystem and terminal to local LLMs (via Ollama) or free state-of-the-art cloud models (via NVIDIA NIM) — no Claude Code, no cloud subscriptions, no IDE required. 

This serves as a local wrapper to use with **free NVIDIA NIM AI models**, allowing for **unlimited LLM usage** at a slower pace (using rate-limit pacing) than large commercial tools like Antigravity and Claude, but **totally free and open source**.

---

## What it does

| Capability | How |
|---|---|
| Read files in allowed folders | `list_dir`, `find_similar_files`, `read_file` |
| Run terminal commands | `run_command` (with safety controls) |
| Capture command output automatically | `subprocess` → fed back to model |
| Write files you can open | `write_file` → always goes into `output/` |
| Ask you a question when confused | `ask_user` → pauses the loop |
| Show its thinking | Ollama & NVIDIA NIM `thinking` field printed if `debug_level: 2` |
| Show system prompt | Printed at startup if `debug_level: 2` |
| Audit log | Every tool call logged to `logs/sessions/session_*.jsonl` |

---

## Requirements

- Python 3.11+
- Two pip packages:
  ```bash
  pip install requests pyyaml
  ```
- **For Local Ollama Mode**:
  - Ollama running locally (`ollama serve` or Ollama.app)
  - Gemma 4 pulled: `ollama pull gemma4`
- **For NVIDIA NIM Mode**:
  - A free NVIDIA developer API key (set in your environment as `NVIDIA_API_KEY` or in `config.yaml` as `nvidia_api_key`)

---

## Quick start

```bash
# 1. Clone / copy this folder somewhere on your Mac
cd ~/local-agent

# 2. Edit config.yaml — set your workspace_roots to real folders and optionally add your nvidia_api_key
nano config.yaml

# 3. Run
python agent.py

# 4. Choose your provider (Ollama or NVIDIA NIM) in the terminal prompt
```

---

## How the whole thing works (plain English)

Think of it as **three layers talking to each other**:

```
YOU  →  agent.py  →  Ollama (Gemma 4) OR NVIDIA NIM (Nemotron 3)
              ↑             ↓
         tool results ← tool calls
              ↑
    files.py / shell.py / writer.py
```

### Step by step for every message you send

1. **You type a request** in the terminal.

2. **agent.py** takes your message and adds it to a running conversation list
   (just a Python list of `{"role": ..., "content": ...}` dicts).

3. **agent.py sends the whole conversation + the tool list** to Ollama's local HTTP API or the NVIDIA NIM API.

4. **The LLM reads your message and the tool descriptions** and decides:
   - *"I can answer directly"* → returns plain text → agent prints it → done.
   - *"I need to look at a file first"* → returns a structured tool call JSON.
   - *"This is ambiguous"* → calls `ask_user` → agent pauses and asks you.

5. **If there is a tool call**, agent.py calls the matching Python function
   (`list_dir`, `run_command`, etc.) and captures the result.

6. **The result is added to the conversation** and sent back to the LLM.

7. **The LLM reads the result** and either answers or calls another tool.

8. **This loop repeats** until the LLM gives a final plain-text answer.

### Free Unlimited NIM Pacing

When running in NVIDIA NIM mode with the free tier, the agent actively paces its requests (with a built-in 3.0s delay between calls) and handles rate limits (HTTP 429/503) with exponential backoff. This allows for **unlimited agent runs** without paying a dime, serving as a slower but totally free and open-source alternative to cloud-metered tools like Antigravity or Claude Code.

### Thinking tokens

Both Gemma 4 and NVIDIA's Nemotron models support native thinking/reasoning output. When `enable_thinking: true` and `debug_level: 2`, the agent prints the model's internal reasoning trace (wrapped in `── 🧠 thinking ──` blocks) before each tool call and before the final answer. This is fully optional and has no effect on the answer quality.

---

## File structure

```
local-agent/
├── agent.py            ← main script, run this
├── config.yaml         ← all settings (model, paths, safety, debug)
├── prompts/
│   └── system.txt      ← instruction prompt given to Gemma at startup
├── tools/
│   ├── files.py        ← list_dir, find_similar_files, read_file, stat_file
│   ├── shell.py        ← run_command with safety controls
│   └── writer.py       ← write_file into output/
├── output/             ← every file the agent creates lands here
├── logs/sessions/      ← one .jsonl audit log per session
└── workspace/          ← (optional) put files here for the agent to read
```

---

## config.yaml explained

```yaml
model: "gemma4:latest"       # exact name from `ollama list`
context_window: 16384        # tokens per call — raise for bigger files
enable_thinking: true        # show <think> trace when debug_level = 2

workspace_roots:             # ONLY these folders can be read
  - "~/Documents"
  - "~/trip-notes"

output_dir: "~/local-agent/output"   # ONLY place files are written
log_dir:    "~/local-agent/logs/sessions"

max_file_bytes: 32000        # max bytes read from one file
max_command_output_chars: 4000
command_timeout: 30          # seconds before a command is killed

confirm_commands:            # these need your y/N before running
  - mv
  - cp
  - sudo
  - pip
  - brew

blocked_commands:            # these are always rejected, no prompt
  - "rm -rf"
  - "dd if="

debug_level: 1               # 0=silent  1=show tools  2=show everything
```

---

## Debug levels

| Level | What you see |
|---|---|
| `0` | Final answer only |
| `1` | Tool name, arguments, result snippet (recommended) |
| `2` | Also prints the full system prompt at startup and the model's thinking tokens |

---

## Tools the agent can call

### `list_dir`
Lists files/folders inside an allowed directory.
> *"What files are in ~/trip-notes?"*

### `find_similar_files`
Searches filenames for keywords.
> *"Find anything about Mount Fuji in ~/Documents"*

### `read_file`
Reads a text file's content (capped at `max_file_bytes`).
> Triggered automatically after `find_similar_files` narrows it down.

### `stat_file`
Reads metadata only (size, modified date) without loading content.

### `run_command`
Runs a shell command and captures stdout + stderr automatically.
> *"How many lines are in that CSV?"* → runs `wc -l file.csv`

### `write_file`
Creates a file in `output/`. You can then open it normally in Finder / VS Code.
> *"Save a summary of the itinerary as a markdown file."*

### `ask_user`
Pauses the agent and asks you a question before continuing.
> Triggered when multiple files match, or a command looks risky.

---

## Example session (debug_level: 1)

```
You: Look in ~/trip-notes and tell me what I'm doing after the Mount Fuji climb.

⚙  Tool: find_similar_files
   query:           Mount Fuji climb
   root:            ~/trip-notes
   result:          [ok]  [{'path': '~/trip-notes/japan-itinerary.md', ...}]

⚙  Tool: read_file
   path:            ~/trip-notes/japan-itinerary.md
   result:          [ok]  ## Day 3 — Mount Fuji ...

● Agent:
After completing the Mount Fuji climb you have a rest afternoon at the
Fujisan Hotel, then dinner at a local restaurant in Fujiyoshida.
The next morning (Day 4) you take the Shinkansen to Kyoto.
```

---

## Extending it

To add a new tool:

1. Write a function in `tools/files.py`, `tools/shell.py`, or a new file.
2. Add a matching entry to the `TOOLS` list in `agent.py` (same JSON schema format).
3. Add a matching `elif name == "your_tool"` branch in the `dispatch()` function.

That is all.

---

## Safety summary

- The agent can only **read** inside `workspace_roots`.
- The agent can only **write** inside `output_dir`.
- Dangerous command patterns are **hard-blocked** (no confirmation offered).
- Commands like `mv`, `sudo`, `pip` need your **explicit y/N** each time.
- Every file read, command run, and file written is logged to `logs/sessions/`.
