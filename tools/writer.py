"""
tools/writer.py
───────────────
File creation / append tool.
The agent can only write inside the configured output_dir.
"""

import os
from pathlib import Path
from datetime import datetime


def _resolve_output(filename: str, output_dir: str) -> Path:
    base = Path(os.path.expanduser(output_dir)).resolve()
    base.mkdir(parents=True, exist_ok=True)
    # Prevent path traversal: strip any directory components from filename
    safe_name = Path(filename).name
    return base / safe_name


def write_file(filename: str, content: str, output_dir: str, append: bool = False) -> dict:
    """
    Write or append content to a file inside output_dir.
    filename: just the filename, no directory traversal allowed.
    """
    target = _resolve_output(filename, output_dir)
    mode = "a" if append else "w"
    try:
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
        return {
            "ok": True,
            "path": str(target),
            "mode": "appended" if append else "created/overwritten",
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
