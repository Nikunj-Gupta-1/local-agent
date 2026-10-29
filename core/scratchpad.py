"""
core/scratchpad.py
──────────────────
Manages persistent task state, subtasks, files modified,
discoveries, and notes during agent execution.
"""

from pathlib import Path
from typing import List, Dict, Any, Set, Optional

SCRATCHPAD_NAME = "scratchpad.md"


class ScratchpadManager:
    def __init__(self, output_dir: Path, workspace_roots: Optional[List[str]] = None):
        self.output_dir = Path(output_dir)
        self.workspace_roots = workspace_roots or []
        self.path = self.output_dir / SCRATCHPAD_NAME
        self.goal = ""
        self.plan: List[Dict[str, Any]] = []
        self.files: Set[str] = set()
        self.discoveries: List[str] = []
        self.notes: List[str] = []
        self.user_prompts: List[str] = []

    def set_output_dir(self, output_dir: Path, workspace_roots: Optional[List[str]] = None):
        self.output_dir = Path(output_dir)
        self.path = self.output_dir / SCRATCHPAD_NAME
        if workspace_roots:
            self.workspace_roots = workspace_roots

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
        p = prompt.strip()
        if p and p not in self.user_prompts:
            self.user_prompts.append(p)
            self.write()

    def add_file(self, filepath: str):
        resolved = Path(filepath).resolve()
        path_str = str(resolved)
        for root in self.workspace_roots:
            try:
                rel = resolved.relative_to(Path(root).resolve())
                path_str = str(rel)
                break
            except ValueError:
                pass

        if resolved.name == SCRATCHPAD_NAME:
            return

        if path_str not in self.files:
            self.files.add(path_str)
            self.write()

    def add_discovery(self, text: str):
        t = text.strip()
        if t and t not in self.discoveries:
            self.discoveries.append(t)
            self.write()

    def add_note(self, text: str):
        t = text.strip()
        if t and t not in self.notes:
            self.notes.append(t)
            self.write()

    def mark_done(self, subtask_id: int):
        for st in self.plan:
            if st["id"] == subtask_id:
                st["done"] = True
        self.write()

    def load_or_init(self, goal: str, subtasks: Optional[List[Dict[str, Any]]] = None):
        self.goal = goal
        if subtasks:
            self.plan = [
                {
                    "id": st["id"],
                    "title": st["title"],
                    "scope": st["scope"],
                    "depends_on": st.get("depends_on", []),
                    "done": st.get("done", False),
                }
                for st in subtasks
            ]
        else:
            self.plan = []
        self.write()

    def build_agent_view(self) -> str:
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

        lines.extend(["", "## Plan Progress"])
        current_found = False
        if self.plan:
            for st in self.plan:
                if st["done"]:
                    lines.append(f"- [x] **[{st['id']}] {st['title']}** (Completed)")
                elif not current_found:
                    lines.append(f"- [/] **[{st['id']}] {st['title']}** (CURRENT FOCUS — Only implement this!) — {st['scope']}")
                    current_found = True
        else:
            lines.append("_(no structured plan — single task mode)_")

        lines.extend(["", "## Files Created/Modified"])
        for f in sorted(self.files):
            lines.append(f"- `{f}`")
        if not self.files:
            lines.append("_(none yet)_")

        lines.extend(["", "## Key Discoveries"])
        for d in self.discoveries:
            lines.append(f"- {d}")
        if not self.discoveries:
            lines.append("_(none yet)_")

        lines.extend(["", "## Notes / Warnings"])
        for n in self.notes:
            lines.append(f"- {n}")
        if not self.notes:
            lines.append("_(none yet)_")

        return "\n".join(lines)

    def write(self):
        lines = [
            "# Agent Scratchpad",
            "",
            "## Goal",
            "",
            self.goal or "(none)",
            "",
            "## User Prompts History",
            "",
        ]
        for idx, p in enumerate(self.user_prompts, 1):
            lines.append(f"{idx}. {p}")
        if not self.user_prompts:
            lines.append("_(none yet)_")

        lines.extend(["", "## Plan", ""])
        for st in self.plan:
            status = "[x]" if st.get("done") else "[ ]"
            lines.append(f"- {status} **[{st['id']}] {st['title']}** — {st['scope']}")
        if not self.plan:
            lines.append("_(no structured plan)_")

        lines.extend(["", "## Files Created/Modified", ""])
        for f in sorted(self.files):
            lines.append(f"- `{f}`")
        if not self.files:
            lines.append("_(none yet)_")

        lines.extend(["", "## Key Discoveries", ""])
        for d in self.discoveries:
            lines.append(f"- {d}")
        if not self.discoveries:
            lines.append("_(none yet)_")

        lines.extend(["", "## Notes / Warnings", ""])
        for n in self.notes:
            lines.append(f"- {n}")
        if not self.notes:
            lines.append("_(none yet)_")
        lines.append("")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "plan": self.plan,
            "files": sorted(list(self.files)),
            "discoveries": self.discoveries,
            "notes": self.notes,
            "user_prompts": self.user_prompts,
        }
