"""
gui/app.py
──────────
Native Desktop GUI for Local Agent.
Built with CustomTkinter for modern macOS curves, dark obsidian palette,
and Antigravity / Codex styling without any browser or web server.
"""

import os
import sys
import json
import yaml
import queue
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.engine import AgentEngine
from core.providers import get_provider
from tools.files import list_dir

# ── Appearance Configuration ──
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Design tokens
CLR_BG = "#0A0C0E"
CLR_SURFACE = "#121519"
CLR_CARD = "#181B20"
CLR_CARD_HOVER = "#20242B"
CLR_INPUT = "#15181E"
CLR_BORDER = "#252932"
CLR_TEXT_MAIN = "#F1F5F9"
CLR_TEXT_MUTED = "#94A3B8"
CLR_CYAN = "#00D2FF"
CLR_BLUE = "#3B82F6"
CLR_PURPLE = "#A855F7"
CLR_GREEN = "#10B981"
CLR_AMBER = "#F59E0B"
CLR_RED = "#EF4444"

FONT_SANS = ("SF Pro Display", 13)
FONT_SANS_BOLD = ("SF Pro Display", 13, "bold")
FONT_TITLE = ("SF Pro Display", 15, "bold")
FONT_MONO = ("JetBrains Mono", 12)
FONT_MONO_SMALL = ("JetBrains Mono", 11)


def load_config() -> Dict[str, Any]:
    cfg_path = PROJECT_ROOT / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(cfg: Dict[str, Any]):
    cfg_path = PROJECT_ROOT / "config.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, engine: AgentEngine, on_save_callback):
        super().__init__(parent)
        self.engine = engine
        self.on_save = on_save_callback
        self.title("AI Source & Application Settings")
        self.geometry("640x700")
        self.resizable(False, False)
        self.configure(fg_color=CLR_BG)

        # Center on parent
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        cfg = load_config()

        # Title
        lbl = ctk.CTkLabel(self, text="AI Sources & Configuration", font=FONT_TITLE, text_color=CLR_TEXT_MAIN)
        lbl.pack(padx=20, pady=(18, 12), anchor="w")

        # Scrollable container
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=5)

        # ── 1. Google Gemini ──
        gemini_box = ctk.CTkFrame(container, fg_color=CLR_CARD, corner_radius=14, border_width=1, border_color=CLR_BORDER)
        gemini_box.pack(fill="x", pady=8, padx=2)

        hdr1 = ctk.CTkFrame(gemini_box, fg_color="transparent")
        hdr1.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hdr1, text="Google Gemini API", font=FONT_SANS_BOLD, text_color=CLR_BLUE).pack(side="left")
        ctk.CTkButton(hdr1, text="Test Connection", width=110, height=26, corner_radius=8, fg_color=CLR_SURFACE,
                       hover_color=CLR_CARD_HOVER, command=lambda: self._test_prov("gemini")).pack(side="right")

        ctk.CTkLabel(gemini_box, text="Gemini API Key:", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(4, 2))
        self.gemini_key_entry = ctk.CTkEntry(gemini_box, show="•", fg_color=CLR_INPUT, border_color=CLR_BORDER)
        self.gemini_key_entry.pack(fill="x", padx=14, pady=2)
        self.gemini_key_entry.insert(0, cfg.get("gemini_api_key", ""))

        ctk.CTkLabel(gemini_box, text="Model:", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(6, 2))
        self.gemini_model_entry = ctk.CTkEntry(gemini_box, fg_color=CLR_INPUT, border_color=CLR_BORDER)
        self.gemini_model_entry.pack(fill="x", padx=14, pady=(2, 10))
        self.gemini_model_entry.insert(0, cfg.get("gemini_model", "gemini-2.5-flash"))

        self.gemini_status = ctk.CTkLabel(gemini_box, text="", font=FONT_MONO_SMALL)
        self.gemini_status.pack(padx=14, pady=(0, 8), anchor="w")

        # ── 2. NVIDIA NIM ──
        nvidia_box = ctk.CTkFrame(container, fg_color=CLR_CARD, corner_radius=14, border_width=1, border_color=CLR_BORDER)
        nvidia_box.pack(fill="x", pady=8, padx=2)

        hdr2 = ctk.CTkFrame(nvidia_box, fg_color="transparent")
        hdr2.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hdr2, text="NVIDIA NIM (Free Tier)", font=FONT_SANS_BOLD, text_color=CLR_GREEN).pack(side="left")
        ctk.CTkButton(hdr2, text="Test Connection", width=110, height=26, corner_radius=8, fg_color=CLR_SURFACE,
                       hover_color=CLR_CARD_HOVER, command=lambda: self._test_prov("nvidia")).pack(side="right")

        ctk.CTkLabel(nvidia_box, text="NVIDIA API Key:", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(4, 2))
        self.nvidia_key_entry = ctk.CTkEntry(nvidia_box, show="•", fg_color=CLR_INPUT, border_color=CLR_BORDER)
        self.nvidia_key_entry.pack(fill="x", padx=14, pady=2)
        self.nvidia_key_entry.insert(0, cfg.get("nvidia_api_key", ""))

        ctk.CTkLabel(nvidia_box, text="Model:", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(6, 2))
        self.nvidia_model_entry = ctk.CTkEntry(nvidia_box, fg_color=CLR_INPUT, border_color=CLR_BORDER)
        self.nvidia_model_entry.pack(fill="x", padx=14, pady=(2, 10))
        self.nvidia_model_entry.insert(0, cfg.get("nvidia_model", "nvidia/nemotron-3-ultra-550b-a55b"))

        self.nvidia_status = ctk.CTkLabel(nvidia_box, text="", font=FONT_MONO_SMALL)
        self.nvidia_status.pack(padx=14, pady=(0, 8), anchor="w")

        # ── 3. Local Ollama ──
        ollama_box = ctk.CTkFrame(container, fg_color=CLR_CARD, corner_radius=14, border_width=1, border_color=CLR_BORDER)
        ollama_box.pack(fill="x", pady=8, padx=2)

        hdr3 = ctk.CTkFrame(ollama_box, fg_color="transparent")
        hdr3.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hdr3, text="Local Ollama", font=FONT_SANS_BOLD, text_color=CLR_CYAN).pack(side="left")
        ctk.CTkButton(hdr3, text="Test Connection", width=110, height=26, corner_radius=8, fg_color=CLR_SURFACE,
                       hover_color=CLR_CARD_HOVER, command=lambda: self._test_prov("ollama")).pack(side="right")

        ctk.CTkLabel(ollama_box, text="Endpoint URL:", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(4, 2))
        self.ollama_url_entry = ctk.CTkEntry(ollama_box, fg_color=CLR_INPUT, border_color=CLR_BORDER)
        self.ollama_url_entry.pack(fill="x", padx=14, pady=2)
        self.ollama_url_entry.insert(0, cfg.get("ollama_url", "http://127.0.0.1:11434"))

        ctk.CTkLabel(ollama_box, text="Model:", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(6, 2))
        self.ollama_model_entry = ctk.CTkEntry(ollama_box, fg_color=CLR_INPUT, border_color=CLR_BORDER)
        self.ollama_model_entry.pack(fill="x", padx=14, pady=(2, 10))
        self.ollama_model_entry.insert(0, cfg.get("model", "gemma4-e4b-64k:latest"))

        self.ollama_status = ctk.CTkLabel(ollama_box, text="", font=FONT_MONO_SMALL)
        self.ollama_status.pack(padx=14, pady=(0, 8), anchor="w")

        # ── 4. LM Studio ──
        lm_box = ctk.CTkFrame(container, fg_color=CLR_CARD, corner_radius=14, border_width=1, border_color=CLR_BORDER)
        lm_box.pack(fill="x", pady=8, padx=2)

        hdr4 = ctk.CTkFrame(lm_box, fg_color="transparent")
        hdr4.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hdr4, text="LM Studio / Local AI", font=FONT_SANS_BOLD, text_color=CLR_PURPLE).pack(side="left")
        ctk.CTkButton(hdr4, text="Test Connection", width=110, height=26, corner_radius=8, fg_color=CLR_SURFACE,
                       hover_color=CLR_CARD_HOVER, command=lambda: self._test_prov("lmstudio")).pack(side="right")

        ctk.CTkLabel(lm_box, text="Base URL:", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(4, 2))
        self.lm_url_entry = ctk.CTkEntry(lm_box, fg_color=CLR_INPUT, border_color=CLR_BORDER)
        self.lm_url_entry.pack(fill="x", padx=14, pady=2)
        self.lm_url_entry.insert(0, cfg.get("openai_base_url", "http://localhost:1234/v1"))

        ctk.CTkLabel(lm_box, text="Model:", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(6, 2))
        self.lm_model_entry = ctk.CTkEntry(lm_box, fg_color=CLR_INPUT, border_color=CLR_BORDER)
        self.lm_model_entry.pack(fill="x", padx=14, pady=(2, 10))
        self.lm_model_entry.insert(0, cfg.get("lm_model", "local-model"))

        self.lm_status = ctk.CTkLabel(lm_box, text="", font=FONT_MONO_SMALL)
        self.lm_status.pack(padx=14, pady=(0, 8), anchor="w")

        # Save Button
        save_btn = ctk.CTkButton(
            self,
            text="Save Settings",
            font=FONT_SANS_BOLD,
            height=38,
            corner_radius=12,
            fg_color=CLR_BLUE,
            hover_color="#2563eb",
            command=self._save_and_close,
        )
        save_btn.pack(fill="x", padx=20, pady=16)

    def _test_prov(self, provider: str):
        cfg = load_config()
        if provider == "gemini":
            cfg["gemini_api_key"] = self.gemini_key_entry.get().strip()
            cfg["model"] = self.gemini_model_entry.get().strip()
            lbl = self.gemini_status
        elif provider == "nvidia":
            cfg["nvidia_api_key"] = self.nvidia_key_entry.get().strip()
            cfg["model"] = self.nvidia_model_entry.get().strip()
            lbl = self.nvidia_status
        elif provider == "ollama":
            cfg["ollama_url"] = self.ollama_url_entry.get().strip()
            cfg["model"] = self.ollama_model_entry.get().strip()
            lbl = self.ollama_status
        elif provider == "lmstudio":
            cfg["openai_base_url"] = self.lm_url_entry.get().strip()
            cfg["model"] = self.lm_model_entry.get().strip()
            lbl = self.lm_status

        lbl.configure(text="Connecting...", text_color=CLR_CYAN)

        def run():
            try:
                p = get_provider(provider, cfg)
                res = p.test_connection()
                if res.get("ok"):
                    self.after(0, lambda: lbl.configure(text=f"✓ {res.get('message')}", text_color=CLR_GREEN))
                else:
                    self.after(0, lambda: lbl.configure(text=f"✗ {res.get('message')}", text_color=CLR_RED))
            except Exception as e:
                self.after(0, lambda: lbl.configure(text=f"✗ Error: {e}", text_color=CLR_RED))

        threading.Thread(target=run, daemon=True).start()

    def _save_and_close(self):
        cfg = load_config()
        cfg["gemini_api_key"] = self.gemini_key_entry.get().strip()
        cfg["gemini_model"] = self.gemini_model_entry.get().strip()
        cfg["nvidia_api_key"] = self.nvidia_key_entry.get().strip()
        cfg["nvidia_model"] = self.nvidia_model_entry.get().strip()
        cfg["ollama_url"] = self.ollama_url_entry.get().strip()
        cfg["openai_base_url"] = self.lm_url_entry.get().strip()
        cfg["lm_model"] = self.lm_model_entry.get().strip()
        save_config(cfg)

        self.on_save()
        self.destroy()


class MemoryDialog(ctk.CTkToplevel):
    def __init__(self, parent, engine: AgentEngine):
        super().__init__(parent)
        self.engine = engine
        self.title("Long-Term Project Memory (RAG)")
        self.geometry("620x550")
        self.configure(fg_color=CLR_BG)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_memories()

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(hdr, text="Indexed Long-Term Memories", font=FONT_TITLE, text_color=CLR_PURPLE).pack(side="left")

        ctk.CTkButton(
            hdr,
            text="Clear Memories",
            width=110,
            height=26,
            corner_radius=8,
            fg_color="#371b1d",
            hover_color="#542327",
            text_color=CLR_RED,
            command=self._clear_all,
        ).pack(side="right")

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=8)

    def _load_memories(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        root = self.engine.workspace_roots[0] if self.engine.workspace_roots else None
        memories = self.engine.memory_store.list_memories(project_path=root)

        if not memories:
            ctk.CTkLabel(
                self.list_frame,
                text="No memories indexed yet.\n\nMemories are automatically recorded when the agent discovers\narchitecture patterns, solves bugs, or reaches task goals!",
                font=FONT_SANS,
                text_color=CLR_TEXT_MUTED,
                justify="center",
            ).pack(pady=40)
            return

        for m in memories:
            card = ctk.CTkFrame(self.list_frame, fg_color=CLR_CARD, corner_radius=10, border_width=1, border_color=CLR_BORDER)
            card.pack(fill="x", pady=4, padx=2)

            chdr = ctk.CTkFrame(card, fg_color="transparent")
            chdr.pack(fill="x", padx=10, pady=(8, 2))

            cat = m.get("category", "info").upper()
            ctk.CTkLabel(chdr, text=cat, font=FONT_MONO_SMALL, text_color=CLR_PURPLE).pack(side="left")

            mem_id = m.get("id")
            ctk.CTkButton(
                chdr,
                text="Delete",
                width=50,
                height=20,
                corner_radius=6,
                fg_color="transparent",
                hover_color=CLR_CARD_HOVER,
                text_color=CLR_RED,
                command=lambda mid=mem_id: self._delete_mem(mid),
            ).pack(side="right")

            txt = ctk.CTkLabel(card, text=m.get("content", ""), font=FONT_SANS, text_color=CLR_TEXT_MAIN, wraplength=520, justify="left")
            txt.pack(padx=10, pady=(2, 8), anchor="w")

    def _delete_mem(self, mem_id: str):
        self.engine.memory_store.delete_memory(mem_id)
        self._load_memories()

    def _clear_all(self):
        if messagebox.askyesno("Confirm Clear", "Clear all long-term memories for this workspace?"):
            root = self.engine.workspace_roots[0] if self.engine.workspace_roots else None
            self.engine.memory_store.clear_memories(project_path=root)
            self._load_memories()


class LocalAgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Local Agent · Codex & Antigravity Edition")
        self.geometry("1240x820")
        self.minsize(980, 640)
        self.configure(fg_color=CLR_BG)

        self.config = load_config()
        self.engine = AgentEngine(self.config)
        self.is_executing = False

        self._build_header()
        self._build_body()
        self._update_file_list()

    def _build_header(self):
        self.header = ctk.CTkFrame(self, height=52, fg_color=CLR_SURFACE, corner_radius=0)
        self.header.pack(fill="x", side="top")

        # ── Left: Project Folder Pill ──
        root_path = self.engine.workspace_roots[0] if self.engine.workspace_roots else "project"
        folder_name = Path(root_path).name or "workspace"

        self.folder_btn = ctk.CTkButton(
            self.header,
            text=f"📁 {folder_name}",
            font=FONT_SANS_BOLD,
            height=30,
            corner_radius=15,
            fg_color=CLR_CARD,
            hover_color=CLR_CARD_HOVER,
            command=self._choose_workspace_folder,
        )
        self.folder_btn.pack(side="left", padx=14, pady=10)

        # ── Center: Provider & Model Selector ──
        provider_names = ["Local Ollama", "Google Gemini", "NVIDIA NIM", "LM Studio"]
        cur_prov = self.config.get("provider", "ollama")
        prov_map = {"ollama": "Local Ollama", "gemini": "Google Gemini", "nvidia": "NVIDIA NIM", "lmstudio": "LM Studio"}

        self.prov_select = ctk.CTkOptionMenu(
            self.header,
            values=provider_names,
            font=FONT_SANS,
            height=30,
            corner_radius=10,
            fg_color=CLR_CARD,
            button_color=CLR_CARD_HOVER,
            command=self._on_provider_change,
        )
        self.prov_select.set(prov_map.get(cur_prov, "Local Ollama"))
        self.prov_select.pack(side="left", padx=6)

        self.model_select = ctk.CTkComboBox(
            self.header,
            values=[self.config.get("model", "gemma4-e4b-64k:latest")],
            font=FONT_SANS,
            height=30,
            width=220,
            corner_radius=10,
            fg_color=CLR_INPUT,
            border_color=CLR_BORDER,
        )
        self.model_select.set(self.config.get("model", "gemma4-e4b-64k:latest"))
        self.model_select.pack(side="left", padx=6)

        # ── Right: Safety, Memory, Plan, Settings ──
        self.settings_btn = ctk.CTkButton(
            self.header,
            text="⚙ Settings",
            width=85,
            height=30,
            corner_radius=10,
            fg_color=CLR_CARD,
            hover_color=CLR_CARD_HOVER,
            command=self._open_settings,
        )
        self.settings_btn.pack(side="right", padx=(4, 14))

        self.plan_btn = ctk.CTkButton(
            self.header,
            text="📋 Plan",
            width=70,
            height=30,
            corner_radius=10,
            fg_color=CLR_CARD,
            hover_color=CLR_CARD_HOVER,
            command=self._toggle_scratchpad,
        )
        self.plan_btn.pack(side="right", padx=4)

        self.memory_btn = ctk.CTkButton(
            self.header,
            text="🧠 Memory",
            width=85,
            height=30,
            corner_radius=10,
            fg_color=CLR_CARD,
            hover_color=CLR_CARD_HOVER,
            command=self._open_memory,
        )
        self.memory_btn.pack(side="right", padx=4)

        # Safety mode segmented button
        self.safety_seg = ctk.CTkSegmentedButton(
            self.header,
            values=["Safe", "Auto", "Strict"],
            height=28,
            corner_radius=14,
            command=self._on_safety_mode_change,
        )
        self.safety_seg.set(self.config.get("safety_mode", "safe").capitalize())
        self.safety_seg.pack(side="right", padx=10)

    def _build_body(self):
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True)

        # ── Left Sidebar ──
        self.sidebar = ctk.CTkFrame(self.body, width=240, fg_color=CLR_SURFACE, corner_radius=12)
        self.sidebar.pack(side="left", fill="y", padx=(12, 6), pady=12)
        self.sidebar.pack_propagate(False)

        new_chat_btn = ctk.CTkButton(
            self.sidebar,
            text="+ New Session",
            font=FONT_SANS_BOLD,
            height=32,
            corner_radius=10,
            fg_color=CLR_CARD,
            hover_color=CLR_CARD_HOVER,
            command=self._reset_session,
        )
        new_chat_btn.pack(fill="x", padx=10, pady=(12, 8))

        ctk.CTkLabel(self.sidebar, text="WORKSPACE FILES", font=FONT_MONO_SMALL, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(10, 4))
        self.files_box = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent")
        self.files_box.pack(fill="both", expand=True, padx=4, pady=4)

        # ── Center: Chat Canvas & Input ──
        self.main_content = ctk.CTkFrame(self.body, fg_color="transparent")
        self.main_content.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=12)

        # Scrollable messages area
        self.messages_scroll = ctk.CTkScrollableFrame(self.main_content, fg_color="transparent")
        self.messages_scroll.pack(fill="both", expand=True)

        # Welcome Empty State
        self.empty_frame = ctk.CTkFrame(self.messages_scroll, fg_color=CLR_CARD, corner_radius=18, border_width=1, border_color=CLR_BORDER)
        self.empty_frame.pack(pady=60, padx=40)
        ctk.CTkLabel(self.empty_frame, text="⚡ Local Agent Ready", font=FONT_TITLE, text_color=CLR_CYAN).pack(pady=(20, 6))
        ctk.CTkLabel(
            self.empty_frame,
            text="Type an instruction below to autonomously plan, code, inspect files, and execute commands.\nAll changes remain strictly within your workspace boundaries with Long-Term Memory RAG enabled.",
            font=FONT_SANS,
            text_color=CLR_TEXT_MUTED,
            justify="center",
        ).pack(padx=24, pady=(0, 20))

        # Bottom Input Area
        self.input_card = ctk.CTkFrame(self.main_content, height=80, fg_color=CLR_CARD, corner_radius=18, border_width=1, border_color=CLR_BORDER)
        self.input_card.pack(fill="x", pady=(10, 4))

        self.input_entry = ctk.CTkTextbox(
            self.input_card,
            font=FONT_SANS,
            fg_color="transparent",
            height=46,
            wrap="word",
        )
        self.input_entry.pack(fill="x", padx=14, pady=(8, 2))
        self.input_entry.bind("<Return>", self._on_enter_press)

        # Actions row inside input card
        actions_row = ctk.CTkFrame(self.input_card, fg_color="transparent", height=28)
        actions_row.pack(fill="x", padx=12, pady=(0, 6))

        self.stop_btn = ctk.CTkButton(
            actions_row,
            text="■ Interrupt",
            font=FONT_SANS_BOLD,
            width=90,
            height=24,
            corner_radius=12,
            fg_color=CLR_RED,
            hover_color="#dc2626",
            command=self._interrupt_agent,
        )
        # Hidden initially

        self.send_btn = ctk.CTkButton(
            actions_row,
            text="▲ Send",
            font=FONT_SANS_BOLD,
            width=70,
            height=24,
            corner_radius=12,
            fg_color=CLR_BLUE,
            hover_color="#2563eb",
            command=self._send_prompt,
        )
        self.send_btn.pack(side="right")

    def _on_enter_press(self, event):
        if not (event.state & 0x1):  # Shift key not held
            self._send_prompt()
            return "break"

    def _choose_workspace_folder(self):
        new_dir = filedialog.askdirectory(initialdir=self.engine.workspace_roots[0], title="Select Project Workspace")
        if new_dir:
            self.engine.set_workspace_root(new_dir)
            self.config["workspace_roots"] = [new_dir]
            save_config(self.config)
            self.folder_btn.configure(text=f"📁 {Path(new_dir).name}")
            self._update_file_list()

    def _update_file_list(self):
        for w in self.files_box.winfo_children():
            w.destroy()
        root = self.engine.workspace_roots[0] if self.engine.workspace_roots else "."
        res = list_dir(root, self.engine.workspace_roots)
        if res.get("ok"):
            for e in res.get("entries", [])[:30]:
                icon = "📁" if e["type"] == "dir" else "📄"
                lbl = ctk.CTkLabel(self.files_box, text=f"{icon} {e['name']}", font=FONT_MONO_SMALL, text_color=CLR_TEXT_MUTED)
                lbl.pack(anchor="w", padx=4, pady=1)

    def _on_provider_change(self, choice: str):
        mapping = {"Local Ollama": "ollama", "Google Gemini": "gemini", "NVIDIA NIM": "nvidia", "LM Studio": "lmstudio"}
        prov = mapping.get(choice, "ollama")
        self.engine.set_provider(prov, self.config)

        # Refresh model suggestions
        models_map = {
            "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"],
            "nvidia": ["nvidia/nemotron-3-ultra-550b-a55b"],
            "ollama": [self.config.get("model", "gemma4-e4b-64k:latest")],
            "lmstudio": [self.config.get("lm_model", "local-model")],
        }
        self.model_select.configure(values=models_map.get(prov, ["default"]))
        self.model_select.set(models_map.get(prov, ["default"])[0])
        # Update engine active model
        self.config["model"] = self.model_select.get()
        self.engine.config["model"] = self.model_select.get()
        self.engine.provider.model = self.model_select.get()

    def _on_safety_mode_change(self, mode: str):
        self.engine.set_safety_mode(mode.lower())

    def _open_settings(self):
        SettingsDialog(self, self.engine, on_save_callback=self._reload_settings)

    def _reload_settings(self):
        self.config = load_config()
        self.engine.config = self.config
        prov = self.config.get("provider", "ollama")
        self.engine.set_provider(prov, self.config)

    def _open_memory(self):
        MemoryDialog(self, self.engine)

    def _toggle_scratchpad(self):
        # Open scratchpad markdown in native editor or show quick alert
        sp_path = self.engine.scratchpad.path
        if sp_path.exists():
            content = sp_path.read_text(encoding="utf-8")
            top = ctk.CTkToplevel(self)
            top.title("Active Scratchpad State")
            top.geometry("560x600")
            txt = ctk.CTkTextbox(top, font=FONT_MONO, fg_color=CLR_BG)
            txt.pack(fill="both", expand=True, padx=12, pady=12)
            txt.insert("1.0", content)
        else:
            messagebox.showinfo("Scratchpad", "Scratchpad is currently empty. Run a task to initialize the plan.")

    def _reset_session(self):
        self.engine.scratchpad.clear()
        for w in self.messages_scroll.winfo_children():
            w.destroy()
        self.empty_frame = ctk.CTkFrame(self.messages_scroll, fg_color=CLR_CARD, corner_radius=18, border_width=1, border_color=CLR_BORDER)
        self.empty_frame.pack(pady=60, padx=40)
        ctk.CTkLabel(self.empty_frame, text="⚡ New Session Started", font=FONT_TITLE, text_color=CLR_CYAN).pack(pady=(20, 6))
        ctk.CTkLabel(self.empty_frame, text="Ask the agent any question or start a new engineering task.", font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(padx=24, pady=(0, 20))

    def _interrupt_agent(self):
        self.engine.interrupt()
        self.stop_btn.pack_forget()

    def _send_prompt(self):
        text = self.input_entry.get("1.0", "end").strip()
        if not text or self.is_executing:
            return

        self.input_entry.delete("1.0", "end")
        if self.empty_frame:
            self.empty_frame.destroy()

        # Render user message
        u_frame = ctk.CTkFrame(self.messages_scroll, fg_color="#1E232B", corner_radius=16, border_width=1, border_color=CLR_BORDER)
        u_frame.pack(anchor="e", pady=8, padx=20)
        ctk.CTkLabel(u_frame, text=text, font=FONT_SANS, text_color=CLR_TEXT_MAIN, wraplength=700, justify="left").pack(padx=16, pady=10)

        # Prepare agent container
        agent_frame = ctk.CTkFrame(self.messages_scroll, fg_color=CLR_CARD, corner_radius=16, border_width=1, border_color=CLR_BORDER)
        agent_frame.pack(fill="x", pady=8, padx=20)

        self.is_executing = True
        self.stop_btn.pack(side="left")

        # Launch execution thread
        threading.Thread(target=self._run_agent_thread, args=(text, agent_frame), daemon=True).start()

    def _run_agent_thread(self, prompt: str, container: ctk.CTkFrame):
        text_label = None
        thinking_box = None
        plan_frame = None

        for event in self.engine.execute_stream(prompt):
            ev_type = event.get("type")

            # 1. Memory recalled
            if ev_type == "memory_recalled":
                items = event.get("items", [])
                self.after(0, self._render_memory_pill, container, items)

            # 2. Intent Routing (Direct vs Plan)
            elif ev_type == "route_selected":
                route = event.get("route", "DIRECT")
                reason = event.get("reason", "")
                if route == "DIRECT":
                    self.after(0, self._render_route_pill, container, route, reason)

            # 3. Status updates (Rate limits / Pacing / Retries)
            elif ev_type == "status":
                msg = event.get("message", "")
                self.after(0, self._render_status_card, container, msg)

            # 4. Error reporting
            elif ev_type == "error":
                err_text = event.get("error", "An unexpected error occurred.")
                self.after(0, self._render_error_card, container, err_text)

            # 5. Plan created
            elif ev_type == "plan_created":
                subtasks = event.get("subtasks", [])
                complexity = event.get("complexity", "medium")
                self.after(0, self._render_plan_card, container, subtasks, complexity)

            # 6. Thinking token
            elif ev_type == "thinking":
                content = event.get("content", "")
                self.after(0, self._append_thinking, container, content)

            # 7. Assistant token
            elif ev_type == "token":
                content = event.get("content", "")
                self.after(0, self._append_text, container, content)

            # 8. Tool Approval Required (Safe/Strict mode)
            elif ev_type == "tool_approval_required":
                action_id = event.get("action_id")
                name = event.get("name")
                args = event.get("args")
                self.after(0, self._render_approval_card, container, action_id, name, args)

            # 9. Ask User
            elif ev_type == "ask_user":
                action_id = event.get("action_id")
                question = event.get("question")
                self.after(0, self._render_ask_user_card, container, action_id, question)

            # 10. Tool Result
            elif ev_type == "tool_result":
                name = event.get("name")
                result = event.get("result")
                self.after(0, self._render_tool_result, container, name, result)

        self.after(0, self._on_finish_execution)

    def _render_route_pill(self, container, route: str, reason: str):
        pill = ctk.CTkFrame(container, fg_color="#0F2432", corner_radius=12, border_width=1, border_color=CLR_CYAN)
        pill.pack(anchor="w", padx=14, pady=4)
        ctk.CTkLabel(pill, text="⚡ Direct Response Mode (Single Turn)", font=FONT_SANS_BOLD, text_color=CLR_CYAN).pack(padx=12, pady=4)

    def _render_status_card(self, container, message: str):
        card = ctk.CTkFrame(container, fg_color="#2D2108", corner_radius=10, border_width=1, border_color=CLR_AMBER)
        card.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(card, text=f"⏳ {message}", font=FONT_SANS, text_color=CLR_AMBER, wraplength=650, justify="left").pack(padx=12, pady=6)

    def _render_error_card(self, container, error: str):
        card = ctk.CTkFrame(container, fg_color="#2B1113", corner_radius=12, border_width=1, border_color=CLR_RED)
        card.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(card, text="⚠️ API Execution Error", font=FONT_SANS_BOLD, text_color=CLR_RED).pack(anchor="w", padx=12, pady=(8, 2))
        err_box = ctk.CTkTextbox(card, font=FONT_MONO_SMALL, height=70, fg_color="#180A0B", text_color="#FCA5A5")
        err_box.pack(fill="x", padx=12, pady=(2, 6))
        err_box.insert("1.0", error)
        ctk.CTkLabel(card, text="💡 Tip: Open Settings (⚙) to test API keys or select an active model in the header.", font=FONT_MONO_SMALL, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(0, 8))

    def _render_memory_pill(self, container, items):
        pill = ctk.CTkFrame(container, fg_color="#2b1a3d", corner_radius=12, border_width=1, border_color=CLR_PURPLE)
        pill.pack(anchor="w", padx=14, pady=6)
        ctk.CTkLabel(pill, text=f"🧠 Recalled {len(items)} past memories from project history", font=FONT_SANS_BOLD, text_color="#d8b4fe").pack(padx=12, pady=4)

    def _render_plan_card(self, container, subtasks, complexity):
        p_frame = ctk.CTkFrame(container, fg_color=CLR_SURFACE, corner_radius=12, border_width=1, border_color=CLR_BORDER)
        p_frame.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(p_frame, text=f"◈ Task Plan ({complexity.upper()})", font=FONT_SANS_BOLD, text_color=CLR_CYAN).pack(anchor="w", padx=12, pady=(8, 4))
        for st in subtasks:
            lbl = ctk.CTkLabel(p_frame, text=f"○ [{st['id']}] {st['title']}", font=FONT_MONO_SMALL, text_color=CLR_TEXT_MUTED)
            lbl.pack(anchor="w", padx=16, pady=2)

    def _append_thinking(self, container, content):
        if not hasattr(container, "_thinking_box"):
            t_frame = ctk.CTkFrame(container, fg_color="#0D0F12", corner_radius=10, border_width=1, border_color=CLR_BORDER)
            t_frame.pack(fill="x", padx=14, pady=6)
            ctk.CTkLabel(t_frame, text="🧠 Thinking Process", font=FONT_MONO_SMALL, text_color=CLR_TEXT_MUTED).pack(anchor="w", padx=10, pady=(6, 2))
            box = ctk.CTkTextbox(t_frame, font=FONT_MONO_SMALL, height=90, fg_color="transparent")
            box.pack(fill="x", padx=10, pady=(2, 6))
            container._thinking_box = box
        container._thinking_box.insert("end", content)
        container._thinking_box.see("end")

    def _append_text(self, container, content):
        if not hasattr(container, "_text_box"):
            box = ctk.CTkTextbox(container, font=FONT_SANS, fg_color="transparent", wrap="word", height=80)
            box.pack(fill="x", padx=14, pady=8)
            container._text_box = box
        container._text_box.insert("end", content)
        container._text_box.see("end")

    def _render_approval_card(self, container, action_id, name, args):
        card = ctk.CTkFrame(container, fg_color=CLR_SURFACE, corner_radius=12, border_width=1, border_color=CLR_AMBER)
        card.pack(fill="x", padx=14, pady=6)

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(hdr, text=f"⚙ Action Approval: {name}", font=FONT_SANS_BOLD, text_color=CLR_AMBER).pack(side="left")

        body = ctk.CTkTextbox(card, font=FONT_MONO_SMALL, height=70, fg_color="#08090C")
        body.pack(fill="x", padx=12, pady=4)
        body.insert("1.0", json.dumps(args, indent=2))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(6, 10))

        def on_auth():
            self.engine.submit_user_response(action_id, {"approved": True})
            btn_row.destroy()
            ctk.CTkLabel(card, text="✓ Action Authorized", font=FONT_SANS_BOLD, text_color=CLR_GREEN).pack(padx=12, pady=4)

        def on_rej():
            self.engine.submit_user_response(action_id, {"approved": False})
            btn_row.destroy()
            ctk.CTkLabel(card, text="✗ Action Rejected", font=FONT_SANS_BOLD, text_color=CLR_RED).pack(padx=12, pady=4)

        ctk.CTkButton(btn_row, text="Authorize", width=90, height=26, corner_radius=8, fg_color=CLR_GREEN, hover_color="#059669", text_color="#000", command=on_auth).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="Reject", width=80, height=26, corner_radius=8, fg_color=CLR_RED, hover_color="#dc2626", command=on_rej).pack(side="left", padx=4)

    def _render_ask_user_card(self, container, action_id, question):
        card = ctk.CTkFrame(container, fg_color=CLR_SURFACE, corner_radius=12, border_width=1, border_color=CLR_CYAN)
        card.pack(fill="x", padx=14, pady=6)

        ctk.CTkLabel(card, text=f"❓ {question}", font=FONT_SANS_BOLD, text_color=CLR_CYAN, wraplength=600, justify="left").pack(padx=12, pady=(10, 6), anchor="w")

        inp_row = ctk.CTkFrame(card, fg_color="transparent")
        inp_row.pack(fill="x", padx=12, pady=(4, 10))

        entry = ctk.CTkEntry(inp_row, font=FONT_SANS, fg_color=CLR_INPUT, border_color=CLR_BORDER)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def on_reply():
            ans = entry.get().strip()
            self.engine.submit_user_response(action_id, {"approved": True, "answer": ans})
            inp_row.destroy()
            ctk.CTkLabel(card, text=f'Replied: "{ans}"', font=FONT_SANS, text_color=CLR_TEXT_MUTED).pack(padx=12, pady=4)

        ctk.CTkButton(inp_row, text="Submit", width=70, height=28, corner_radius=8, fg_color=CLR_BLUE, command=on_reply).pack(side="right")

    def _render_tool_result(self, container, name, result):
        card = ctk.CTkFrame(container, fg_color=CLR_SURFACE, corner_radius=10, border_width=1, border_color=CLR_BORDER)
        card.pack(fill="x", padx=14, pady=4)
        ok = result.get("ok", True)
        ctk.CTkLabel(card, text=f"⚙ {name} [{'OK' if ok else 'ERROR'}]", font=FONT_MONO_SMALL, text_color=CLR_GREEN if ok else CLR_RED).pack(anchor="w", padx=10, pady=(6, 2))
        res_box = ctk.CTkTextbox(card, font=FONT_MONO_SMALL, height=60, fg_color="#08090C")
        res_box.pack(fill="x", padx=10, pady=(2, 6))
        res_box.insert("1.0", json.dumps(result, indent=2))

    def _on_finish_execution(self):
        self.is_executing = False
        self.stop_btn.pack_forget()
        self._update_file_list()


def launch_gui():
    app = LocalAgentApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
