"""
tools/files.py
──────────────
Filesystem tools: list, search, read, stat.
All paths are checked against config workspace_roots before access.
"""

import os
import fnmatch
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def _resolve(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def _is_allowed(path: str, roots: list[str]) -> bool:
    """Return True only if path is inside one of the allowed workspace roots."""
    target = _resolve(path)
    for root in roots:
        if str(target).startswith(str(_resolve(root))):
            return True
    return False


def _guard(path: str, roots: list[str]) -> Path:
    if not _is_allowed(path, roots):
        raise PermissionError(
            f"Path '{path}' is outside allowed workspace roots: {roots}"
        )
    return _resolve(path)


# ── tools ────────────────────────────────────────────────────────────────────

def list_dir(path: str, roots: list[str]) -> dict:
    """
    List files and subdirectories inside an allowed path.
    Returns a dict with 'entries' (list of dicts with name, type, size_bytes).
    """
    p = _guard(path, roots)
    if not p.exists():
        return {"ok": False, "error": f"Path does not exist: {path}"}
    if not p.is_dir():
        return {"ok": False, "error": f"Not a directory: {path}"}

    entries = []
    for item in sorted(p.iterdir()):
        entry = {
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
        }
        if item.is_file():
            entry["size_bytes"] = item.stat().st_size
        entries.append(entry)

    return {"ok": True, "path": str(p), "entries": entries}


def find_similar_files(query: str, root: str, roots: list[str], max_results: int = 10) -> dict:
    """
    Walk the root directory and return files whose name or path contains
    any word from the query (case-insensitive).
    """
    p = _guard(root, roots)
    if not p.exists():
        return {"ok": False, "error": f"Root does not exist: {root}"}

    words = [w.lower() for w in query.split() if len(w) > 2]
    matches = []

    for filepath in p.rglob("*"):
        if not filepath.is_file():
            continue
        name_lower = filepath.name.lower()
        if any(w in name_lower for w in words):
            matches.append({
                "path": str(filepath),
                "name": filepath.name,
                "size_bytes": filepath.stat().st_size,
            })
        if len(matches) >= max_results:
            break

    return {"ok": True, "query": query, "matches": matches}


def read_file(path: str, roots: list[str], max_bytes: int = 32000) -> dict:
    """
    Read a text file and return its content (up to max_bytes).
    """
    p = _guard(path, roots)
    if not p.exists():
        return {"ok": False, "error": f"File does not exist: {path}"}
    if not p.is_file():
        return {"ok": False, "error": f"Not a file: {path}"}

    raw = p.read_bytes()
    truncated = len(raw) > max_bytes
    chunk = raw[:max_bytes]

    try:
        content = chunk.decode("utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "error": f"Could not decode file: {exc}"}

    return {
        "ok": True,
        "path": str(p),
        "content": content,
        "truncated": truncated,
        "total_bytes": len(raw),
        "returned_bytes": len(chunk),
    }


def stat_file(path: str, roots: list[str]) -> dict:
    """Return metadata about a file without reading its content."""
    p = _guard(path, roots)
    if not p.exists():
        return {"ok": False, "error": f"Path does not exist: {path}"}
    s = p.stat()
    import datetime
    return {
        "ok": True,
        "path": str(p),
        "size_bytes": s.st_size,
        "modified": datetime.datetime.fromtimestamp(s.st_mtime).isoformat(),
        "is_dir": p.is_dir(),
        "suffix": p.suffix,
        "total_lines": sum(1 for _ in p.open("rb")) if p.is_file() else None,
    }


def read_file_lines(path: str, roots: list[str], start_line: int, end_line: int) -> dict:
    """
    Read a specific inclusive line range from a text file (1-indexed).
    Use this instead of read_file when you only need part of a large file.
    This is the preferred tool for inspecting large files to preserve context.
    """
    p = _guard(path, roots)
    if not p.exists():
        return {"ok": False, "error": f"File does not exist: {path}"}
    if not p.is_file():
        return {"ok": False, "error": f"Not a file: {path}"}
    if start_line < 1:
        return {"ok": False, "error": "start_line must be >= 1"}
    if end_line < start_line:
        return {"ok": False, "error": "end_line must be >= start_line"}

    try:
        all_lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except Exception as exc:
        return {"ok": False, "error": f"Could not read file: {exc}"}

    total_lines = len(all_lines)
    # Clamp to actual file length
    end_line = min(end_line, total_lines)
    selected = all_lines[start_line - 1 : end_line]

    return {
        "ok": True,
        "path": str(p),
        "start_line": start_line,
        "end_line": end_line,
        "total_lines": total_lines,
        "content": "".join(selected),
    }
