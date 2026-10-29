#!/usr/bin/env python3
"""
run_app.py
──────────
One-click native desktop application launcher for Local Agent.
Launches the standalone macOS desktop window (Antigravity & Codex styled).
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    if "--web" in sys.argv:
        # Optional web-mode fallback
        from server.api import app
        print("Starting Local Agent in Web Mode on http://127.0.0.1:5000...")
        app.run(host="127.0.0.1", port=5000, debug=False)
    else:
        # Native Desktop Application (Default)
        from gui.app import launch_gui
        print("""
╔═══════════════════════════════════════════════════════════════╗
║                   Local Agent Desktop App                     ║
║      Ollama · Gemini · NVIDIA NIM · LM Studio · Memory RAG    ║
╚═══════════════════════════════════════════════════════════════╝
Opening native desktop window...
        """)
        launch_gui()


if __name__ == "__main__":
    main()
