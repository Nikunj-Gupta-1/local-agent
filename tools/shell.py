"""
tools/shell.py
──────────────
Shell execution wrapper with safety controls.
The agent calls run_command(); the Python layer decides whether
to actually run it, confirm it, or block it.
"""

import subprocess
import shlex
import time


def _check_blocked(cmd: str, blocked: list[str]) -> str | None:
    """Return the matched blocked pattern, or None if safe."""
    for pattern in blocked:
        if pattern in cmd:
            return pattern
    return None


def _check_confirm(cmd: str, confirm_list: list[str]) -> str | None:
    """Return the matched confirm-needed prefix, or None."""
    first_token = cmd.strip().split()[0] if cmd.strip() else ""
    for token in confirm_list:
        if first_token == token or cmd.strip().startswith(token + " "):
            return token
    return None


def run_command(
    cmd: str,
    blocked: list[str],
    confirm_list: list[str],
    timeout: int = 30,
    max_output_chars: int = 4000,
    auto_confirm: bool = False,
) -> dict:
    """
    Execute a shell command safely.

    Returns a dict with:
      ok, cmd, stdout, stderr, exit_code, duration_ms
      or: ok=False, blocked=True / needs_confirm=True
    """

    # 1. Block check
    blocked_hit = _check_blocked(cmd, blocked)
    if blocked_hit:
        return {
            "ok": False,
            "blocked": True,
            "reason": f"Command contains blocked pattern: '{blocked_hit}'",
            "cmd": cmd,
        }

    # 2. Confirm check
    confirm_hit = _check_confirm(cmd, confirm_list)
    if confirm_hit and not auto_confirm:
        return {
            "ok": False,
            "needs_confirm": True,
            "reason": f"Command starts with '{confirm_hit}' — needs your approval",
            "cmd": cmd,
        }

    # 3. Execute
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        stdout = result.stdout[:max_output_chars]
        stderr = result.stderr[:max_output_chars]

        return {
            "ok": True,
            "cmd": cmd,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
            "duration_ms": duration_ms,
            "truncated": len(result.stdout) > max_output_chars,
        }

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "cmd": cmd,
            "error": f"Command timed out after {timeout}s",
            "exit_code": -1,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "cmd": cmd,
            "error": str(exc),
            "exit_code": -1,
            "duration_ms": 0,
        }
