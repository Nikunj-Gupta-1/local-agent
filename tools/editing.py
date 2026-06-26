import os
import shutil
from pathlib import Path
from datetime import datetime


def _resolve(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def _is_allowed(path: str, roots: list[str]) -> bool:
    target = _resolve(path)
    for root in roots:
        root_path = _resolve(root)
        if str(target).startswith(str(root_path)):
            return True
    return False


def _guard(path: str, roots: list[str]) -> Path:
    if not _is_allowed(path, roots):
        raise PermissionError(
            f"Path '{path}' is outside allowed workspace roots: {roots}"
        )
    return _resolve(path)


def edit_file_lines(
    path: str,
    start_line: int,
    end_line: int,
    new_text: str,
    roots: list[str],
    create_backup: bool = True,
) -> dict:
    """
    Replace a line range in a text file.
    Lines are 1-indexed and inclusive.
    """

    p = _guard(path, roots)

    if not p.exists():
        return {"ok": False, "error": f"File does not exist: {path}"}
    if not p.is_file():
        return {"ok": False, "error": f"Not a file: {path}"}
    if start_line < 1 or end_line < start_line:
        return {"ok": False, "error": f"Invalid line range: {start_line}-{end_line}"}

    try:
        original_text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "error": "File is not valid UTF-8 text"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    lines = original_text.splitlines(keepends=True)
    total_lines = len(lines)

    if start_line > total_lines:
        return {
            "ok": False,
            "error": f"start_line {start_line} is beyond end of file ({total_lines} lines)",
        }

    end_line = min(end_line, total_lines)

    replacement_lines = new_text.splitlines(keepends=True)
    if new_text and not new_text.endswith("\n"):
        if replacement_lines:
            replacement_lines[-1] = replacement_lines[-1] + "\n"
        else:
            replacement_lines = ["\n"]

    original_segment = "".join(lines[start_line - 1:end_line])
    new_lines = lines[:start_line - 1] + replacement_lines + lines[end_line:]
    updated_text = "".join(new_lines)

    backup_path = None
    try:
        if create_backup:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = str(p.with_suffix(p.suffix + f".{ts}.bak"))
            shutil.copy2(p, backup_path)

        p.write_text(updated_text, encoding="utf-8")

        return {
            "ok": True,
            "path": str(p),
            "backup_path": backup_path,
            "start_line": start_line,
            "end_line": end_line,
            "original_line_count": total_lines,
            "new_line_count": len(new_lines),
            "original_excerpt": original_segment[:500],
            "new_excerpt": new_text[:500],
        }
    except Exception as exc:
        if backup_path and os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, p)
            except Exception:
                pass
        return {"ok": False, "error": str(exc), "backup_path": backup_path}