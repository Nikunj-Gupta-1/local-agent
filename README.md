# Local Agent Desktop App

A powerful local autonomous coding agent equipped with a modern macOS desktop interface styled like Google Antigravity and OpenAI Codex, multi-provider AI support (Google Gemini, NVIDIA NIM, Ollama, LM Studio, OpenAI-compatible), and 100% local Long-Term Agent Memory RAG.

---

## Highlights

* **Desktop Application GUI**: macOS design language with rounded corners (`rounded-2xl`), dark obsidian palette, translucent frosted glass, collapsible thinking token traces, and live task plan checklists.
* **Multi-Provider AI Sources**:
  * **Google Gemini API**: Native function calling, streaming, and models (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite`).
  * **NVIDIA NIM**: Free tier cloud models with automated rate pacing and backoff.
  * **Local / Remote Ollama**: Gemma 4, DeepSeek-R1, Llama 3, and local models via `http://localhost:11434`.
  * **LM Studio & Local AI**: Universal OpenAI-compatible endpoint support (`http://localhost:1234/v1`, vLLM, Jan, LocalAI, OpenRouter, Groq).
* **AI Source Setup Screen**: Dedicated GUI settings modal to configure API keys, endpoints, and test connections with real-time feedback.
* **Long-Term Agent Memory RAG**: In-process local vector & keyword store that remembers past project decisions, bug fixes, and architectural notes across sessions with auto-injection and on-demand recall.
* **Human-in-the-Loop Safety Controls**:
  * **Safe Mode**: Reads auto-run; shell commands and file mutations display an interactive **[Authorize]** / **[Reject]** card.
  * **Auto Mode**: Autonomous execution for trusted workflows.
  * **Strict Mode**: Requires approval for every tool execution.
  * **Interrupt Button**: Instantly pause the agent and submit a redirection prompt.

---

## Quick Start

### 1. Launch the Desktop Application

Run the launcher from your terminal:
```bash
./run_app.py
```
Or with python:
```bash
python3 run_app.py
```

This starts the local engine and opens the desktop interface in an app-mode window at `http://127.0.0.1:5000`.

### 2. Configure Your AI Sources

Click the **Settings (⚙)** icon in the top right to configure:
* **Google Gemini**: Paste your Gemini API key and click **Test Connection**.
* **NVIDIA NIM**: Paste your NVIDIA Developer API key.
* **Ollama**: Default `http://127.0.0.1:11434`.
* **LM Studio**: Default `http://localhost:1234/v1`.

### 3. CLI Mode (Optional)

If you ever wish to run in the terminal only:
```bash
python3 agent.py
```

---

## Architecture Overview

```
local-agent/
├── run_app.py           ← Desktop app launcher
├── agent.py             ← Classic CLI agent
├── config.yaml          ← Configuration settings
├── core/
│   ├── engine.py        ← Decoupled streaming agent execution loop
│   ├── planner.py       ← Autonomous task planner pass
│   ├── evaluator.py     ← Satisfaction evaluator
│   ├── scratchpad.py    ← Persistent scratchpad manager
│   ├── tools_schema.py  ← Function schemas for all tools
│   ├── memory/
│   │   ├── store.py     ← SQLite vector & hybrid semantic memory
│   │   ├── indexer.py   ← Session memory harvester
│   │   └── hook.py      ← Context injection hook
│   └── providers/
│       ├── base.py      ← Abstract BaseProvider interface
│       ├── gemini_provider.py
│       ├── nvidia_provider.py
│       ├── ollama_provider.py
│       └── openai_compatible_provider.py
├── server/
│   ├── api.py           ← Flask REST API & Server-Sent Events (SSE) server
│   └── static/
│       ├── index.html   ← macOS Antigravity/Codex desktop UI
│       ├── style.css    ← Design tokens, curves, glassmorphism
│       └── app.js       ← Streaming client & state management
├── tools/               ← Filesystem, shell, editing, notify, memory tools
├── tests/               ← Unit test suite (11 passing tests)
└── output/              ← Target directory for created files
```

---

## Running Automated Tests

Run the unit test suite:
```bash
./venv/bin/python -m unittest discover tests
```
