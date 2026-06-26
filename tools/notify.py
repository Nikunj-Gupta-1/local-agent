import shutil
import subprocess


def _clean(s: str) -> str:
    return str(s).replace("\n", " ").strip()


def alert_user(title: str, message: str) -> dict:
    title = _clean(title)[:120]
    message = _clean(message)[:300]

    terminal_notifier = shutil.which("terminal-notifier")

    if terminal_notifier:
        try:
            subprocess.run(
                [
                    terminal_notifier,
                    "-title", title,
                    "-message", message,
                    "-activate", "com.apple.Terminal",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return {
                "ok": True,
                "backend": "terminal-notifier",
                "title": title,
                "message": message,
            }
        except Exception as e:
            last_error = str(e)
    else:
        last_error = "terminal-notifier not installed"

    script = f'display notification "{message.replace(chr(34), "\\\"")}" with title "{title.replace(chr(34), "\\\"")}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        return {
            "ok": True,
            "backend": "osascript",
            "title": title,
            "message": message,
            "note": "If notifications do not appear, enable notification permissions for Terminal/iTerm or the host app.",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "fallback_error": last_error,
            "title": title,
            "message": message,
        }