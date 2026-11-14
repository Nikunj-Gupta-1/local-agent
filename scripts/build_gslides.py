#!/usr/bin/env python3
"""
Builds the Local Agent presentation as a Google Slides batch (docs/slides_batch.json).
Speaker notes are read from docs/presentation_notes.md.
Run: ./venv/bin/python scripts/build_gslides.py && gslides mutate batch <ID> -f docs/slides_batch.json
"""
import json, re, sys

DELETE = sys.argv[1:]  # optional extra element IDs to delete on slide p

BG, CARD, CARD2, LINE = "#0B0D12", "#13161E", "#191D27", "#262B37"
WHITE, TEXT, MUTED, DIM = "#FFFFFF", "#E6E8EE", "#9AA3B4", "#5F6879"
BLUE, TEAL, AMBER, PINK, GREEN, RED = "#8AA4FF", "#5EEAD4", "#FBBF24", "#F472B6", "#4ADE80", "#F87171"
SANS, MONO = "Inter", "JetBrains Mono"
W, H = 720, 405

ops = [{"op": "delete-element", "element": e} for e in ["i0", "i1", *DELETE]]
_n = [0]


def uid(p="E"):
    _n[0] += 1
    return f"{p}{_n[0]}"


def tb(s, text, x, y, w, h, size=12, color=TEXT, bold=False, font=SANS, align="left", valign="TOP", ls=None, bg=None):
    o = {"op": "add-textbox", "slide": s, "text": text, "x": x, "y": y, "width": w, "height": h,
         "font_size": size, "color": color, "bold": bold, "font_family": font,
         "alignment": align, "content_alignment": valign}
    if ls:
        o["line_spacing"] = ls
    if bg:
        o["background_color"] = bg
    ops.append(o)


def shape(s, x, y, w, h, fill, outline=None, kind="ROUND_RECTANGLE", weight=1, alpha=None):
    i = uid("S")
    o = {"op": "add-shape", "slide": s, "shape_type": kind, "x": x, "y": y, "width": w, "height": h,
         "background_color": fill, "id": i}
    if alpha is not None:
        o["alpha"] = alpha
    ops.append(o)
    ops.append({"op": "style-shape", "element": i, "outline_color": outline or fill,
                "outline_weight": weight if outline else 0.1})
    return i


def card(s, x, y, w, h, fill=CARD, outline=LINE):
    return shape(s, x, y, w, h, fill, outline)


def bar(s, x, y, w, h, color):
    return shape(s, x, y, w, h, color, None, "RECTANGLE")


def line(s, x, y, w, h, color=DIM, weight=1.5, arrow=True, dash="SOLID"):
    ops.append({"op": "add-line", "slide": s, "x": x, "y": y, "width": w, "height": h, "color": color,
                "line_weight": weight, "end_arrow": "FILL_ARROW" if arrow else "NONE", "dash_style": dash})


def connect(s, a, b, sa, sb, color=DIM, weight=1.5):
    ops.append({"op": "add-line", "slide": s, "x": 0, "y": 0, "width": 10, "height": 10, "color": color,
                "line_weight": weight, "end_arrow": "FILL_ARROW", "start_connect": a, "end_connect": b,
                "start_site": sa, "end_site": sb, "line_category": "BENT"})


def chip(s, text, x, y, w, color, h=20, size=9, fg=BG):
    shape(s, x, y, w, h, color)
    tb(s, text, x, y, w, h, size, fg, True, SANS, "center", "MIDDLE")


def dot(s, n, x, y, color, d=22, size=10):
    shape(s, x, y, d, d, color, kind="ELLIPSE")
    tb(s, str(n), x - 2, y, d + 4, d, size, BG, True, SANS, "center", "MIDDLE")


def frame(s, num, section, title, sub=None):
    ops.append({"op": "set-background", "slide": s, "color": BG})
    tb(s, f"{num:02d}   {section.upper()}", 36, 22, 420, 18, 9, BLUE, True, MONO)
    tb(s, title, 36, 40, 648, 38, 22, WHITE, True)
    if sub:
        tb(s, sub, 36, 74, 648, 24, 11, MUTED)
    tb(s, "Local Agent", 36, 382, 200, 14, 8, DIM)
    tb(s, f"{num} / 10", W - 136, 382, 100, 14, 8, DIM, False, SANS, "right")


slides = ["p"]


def new():
    i = f"SLIDE_{len(slides) + 1}"
    ops.append({"op": "add-slide", "layout": "BLANK", "id": i})
    slides.append(i)
    return i


# ── 1 · Title ──────────────────────────────────────────────────────────────
s = "p"
ops.append({"op": "set-background", "slide": s, "color": BG})
shape(s, 430, -120, 420, 420, BLUE, kind="ELLIPSE", alpha=0.10)
shape(s, 520, 40, 260, 260, TEAL, kind="ELLIPSE", alpha=0.07)
tb(s, "AUTONOMOUS DESKTOP AI SYSTEM", 48, 56, 340, 16, 9, BLUE, True, MONO)
tb(s, "Local Agent", 48, 76, 560, 68, 50, WHITE, True)
tb(s, "Privacy-Preserving Autonomous Coding for Local and Cloud Models",
   48, 146, 580, 30, 16, TEXT, True)
tb(s, "Inspired by early Antigravity and Codex workflows — unifying their divided capabilities so local models can perform complex tasks in privacy-critical workspaces.",
   48, 178, 560, 42, 11.5, MUTED, ls=125)
x = 48
for label, col in [("Ollama", TEAL), ("LM Studio", BLUE), ("Google Gemini", AMBER), ("NVIDIA NIM", GREEN)]:
    w = 18 + 6.2 * len(label)
    shape(s, x, 232, w, 22, CARD2, col)
    tb(s, label, x, 232, w, 22, 9, col, True, SANS, "center", "MIDDLE")
    x += w + 8
bar(s, 48, 298, 624, 0.75, LINE)
tb(s, "PROJECT TEAM", 48, 310, 200, 14, 8, DIM, True, MONO)
for i, nm in enumerate(["Nikunj Gupta", "Aakarsh", "Shayan", "Uzair"]):
    tb(s, nm, 48 + i * 156, 328, 150, 22, 13, WHITE, True)

# ── 2 · Motivation & Background ────────────────────────────────────────────
s = new()
frame(s, 2, "Motivation & Background",
      "Bringing Cloud-Grade Autonomy to Private Workspaces",
      "Commercial tools split these capabilities across separate cloud apps; sensitive fields like cybersecurity need them locally.")
probs = [
    ("Empowering Local Models",
     "Smaller local models struggle when given large tasks all at once.",
     "Structured task decomposition and state tracking help local models complete complex work.",
     BLUE),
    ("Privacy & Cybersecurity",
     "Sensitive code and security data cannot be sent to external clouds where they may be misused.",
     "All file operations, terminal commands, and long-term memory remain on the local machine.",
     TEAL),
    ("Planning Overhead",
     "Many agents run a slow multi-step planning pass even on simple questions.",
     "A two-stage router sends direct questions straight to the model and plans only when needed.",
     AMBER),
    ("Fragmented Ecosystems",
     "Capabilities are often split across tools or locked to a single model vendor.",
     "One interface connects local engines (Ollama, LM Studio) and cloud APIs (Gemini, NVIDIA NIM).",
     PINK),
]
cw, ch = 318, 112
for i, (t, p, a, col) in enumerate(probs):
    x = 36 + (i % 2) * (cw + 12)
    y = 104 + (i // 2) * (ch + 12)
    card(s, x, y, cw, ch)
    tb(s, f"0{i+1}", x + 14, y + 10, 40, 16, 9.5, col, True, MONO)
    tb(s, t, x + 14, y + 25, cw - 28, 20, 14, WHITE, True)
    tb(s, p, x + 14, y + 46, cw - 28, 26, 9.5, MUTED, ls=115)
    bar(s, x + 14, y + 74, cw - 28, 0.75, LINE)
    tb(s, "→  " + a, x + 14, y + 79, cw - 28, 30, 9.5, col, True, ls=115)
stats = [("4", "model backends"), ("3", "safety modes"), ("2", "routing stages"), ("15", "automated tests")]
for i, (n, l) in enumerate(stats):
    x = 36 + i * 162
    tb(s, n, x, 350, 40, 26, 19, WHITE, True)
    tb(s, l, x + 34, 355, 120, 18, 10, MUTED)

# ── 3 · Architecture ───────────────────────────────────────────────────────
s = new()
frame(s, 3, "System Architecture",
      "Architecture and Event-Streaming Pipeline",
      "A background execution engine streams typed events to the desktop interface so the window remains responsive.")


def node(s, x, y, w, h, t, sub, col, fill=CARD):
    i = card(s, x, y, w, h, fill, col if fill != CARD else LINE)
    bar(s, x + 12, y + 12, 18, 3, col)
    tb(s, t, x + 8, y + 18, w - 16, 20, 11.5, WHITE, True)
    tb(s, sub, x + 8, y + 38, w - 16, 30, 8.5, MUTED, ls=115)
    return i


nw, nh = 112, 72
g = node(s, 36, 140, nw, nh, "Desktop UI", "CustomTkinter\nmain thread", BLUE)
e = node(s, 170, 140, nw, nh, "Core Engine", "core/engine.py\nworker thread", BLUE, CARD2)
r = node(s, 304, 140, nw, nh, "Intent Router", "core/classifier.py\nDIRECT or PLAN", TEAL)
d = node(s, 438, 108, nw, 60, "Direct Path", "single-pass stream", TEAL)
pp = node(s, 438, 184, nw, 60, "Planning Path", "decompose & verify", AMBER)
pv = node(s, 572, 140, nw, nh, "Model Layer", "Ollama · LM Studio\nGemini · NVIDIA", GREEN)
connect(s, g, e, 3, 1, BLUE)
connect(s, e, r, 3, 1, BLUE)
connect(s, r, d, 3, 1, TEAL)
connect(s, r, pp, 3, 1, AMBER)
connect(s, d, pv, 3, 1, TEAL)
connect(s, pp, pv, 3, 1, AMBER)
tb(s, "SUPPORTING SUBSYSTEMS", 36, 262, 300, 14, 8, DIM, True, MONO)
for i, (t, b, col) in enumerate([("Local Memory", "SQLite store recalled into prompts", AMBER),
                                 ("Workspace Tools", "files · shell · scratchpad · recall", TEAL),
                                 ("Approval Gate", "pauses for user authorization", PINK)]):
    x = 36 + i * 218
    card(s, x, 278, 208, 40)
    shape(s, x + 12, 294, 8, 8, col, kind="ELLIPSE")
    tb(s, t, x + 26, 280, 96, 36, 10.5, WHITE, True, valign="MIDDLE")
    tb(s, b, x + 106, 280, 98, 36, 8.5, MUTED, valign="MIDDLE")
card(s, 36, 328, 648, 40, CARD2, LINE)
tb(s, "streamed events  →  route_selected · thinking · token · tool_approval_required · tool_result · complete",
   48, 328, 630, 40, 9.5, TEXT, False, MONO, valign="MIDDLE")

# ── 4 · Router ─────────────────────────────────────────────────────────────
s = new()
frame(s, 4, "Intent Classification",
      "Two-Stage Prompt Routing",
      "Rule-based matching handles clear cases in zero time; the model is queried only when intent is ambiguous.")
steps = [
    ("Multi-step task patterns", "refactor · migrate · build/create … app/service/module · find and fix", "PLAN", AMBER),
    ("Direct question patterns", "greetings · what is · explain · how to · compare · math expressions", "DIRECT", TEAL),
    ("Short queries", "under 35 characters without action verbs (fix, build, create, test, run, edit, write)", "DIRECT", TEAL),
    ("Model classification fallback", "single-word reply (PLAN or DIRECT) at temperature 0 · defaults to DIRECT on error", "PLAN / DIRECT", BLUE),
]
for i, (t, b, res, col) in enumerate(steps):
    y = 108 + i * 66
    card(s, 36, y, 380, 54)
    dot(s, i + 1, 48, y + 16, WHITE)
    tb(s, t, 80, y + 6, 330, 20, 11.5, WHITE, True)
    tb(s, b, 80, y + 26, 330, 26, 8.8, MUTED)
    line(s, 420, y + 27, 22, 0, col, 1.5)
    cwid = 64 if len(res) < 8 else 86
    chip(s, res, 446, y + 17, cwid, col)
    if i < 3:
        line(s, 59, y + 54, 0, 12, DIM, 1)
tb(s, "VERIFIED CLASSIFIER OUTPUTS", 548, 108, 140, 14, 8, DIM, True, MONO)
for i, (p, rr, col) in enumerate([("hello", "DIRECT", TEAL),
                                  ("tell me how i can multiply 2 matrices", "DIRECT", TEAL),
                                  ("refactor the auth module", "PLAN", AMBER),
                                  ("build a new REST api service", "PLAN", AMBER)]):
    y = 126 + i * 60
    card(s, 548, y, 136, 52)
    tb(s, p, 554, y + 4, 124, 28, 8.5, TEXT, False, MONO)
    tb(s, "→ " + rr, 554, y + 32, 124, 16, 8.5, col, True, MONO)

# ── 5 · Plan path ──────────────────────────────────────────────────────────
s = new()
frame(s, 5, "Task Decomposition",
      "Structured Planning for Local and Cloud Models",
      "Breaking complex work into small, scoped steps helps smaller local models succeed without losing context.")
pipe = [
    ("Task Planner", "core/planner.py", "Reads workspace files and session notes. Outputs JSON with complexity and ordered subtasks.", BLUE),
    ("Subtask Loop", "core/engine.py", "Runs each subtask in an isolated conversation of up to 10 turns with tool access.", TEAL),
    ("Evaluator", "core/evaluator.py", "Reviews tool usage and output to judge whether meaningful progress was made.", AMBER),
    ("Scratchpad", "scratchpad.md", "Tracks the goal, modified files, discoveries, and completed steps across every turn.", PINK),
    ("Memory Save", "core/memory/", "Indexes discoveries, notes, and the solution summary into local storage at completion.", GREEN),
]
cw, gap = 120, 12
for i, (t, f, b, col) in enumerate(pipe):
    x = 36 + i * (cw + gap)
    card(s, x, 108, cw, 164)
    dot(s, i + 1, x + 12, 120, col)
    tb(s, t, x + 8, 148, cw - 16, 20, 11.5, WHITE, True)
    tb(s, f, x + 8, 166, cw - 16, 14, 7.5, col, False, MONO)
    tb(s, b, x + 8, 184, cw - 16, 84, 8.8, MUTED, ls=118)
    if i < 4:
        line(s, x + cw + 1, 190, gap - 2, 0, DIM, 1.25)
tb(s, "FAULT-TOLERANT PARSING FOR LOCAL MODELS", 36, 284, 340, 14, 8, DIM, True, MONO)
for i, (t, b) in enumerate([("Pattern-based JSON extraction", "isolates valid JSON even when a model adds conversational text"),
                            ("Single-task fallback", "executes the request as one task if plan generation fails"),
                            ("Non-blocking evaluation", "continues smoothly if the evaluator output cannot be parsed")]):
    x = 36 + i * 218
    card(s, x, 302, 208, 64, CARD2)
    tb(s, t, x + 10, 310, 190, 18, 10.5, WHITE, True)
    tb(s, b, x + 10, 330, 190, 30, 8.8, MUTED, ls=115)

# ── 6 · Providers ──────────────────────────────────────────────────────────
s = new()
frame(s, 6, "Model Abstraction",
      "Unified Interface Across Local and Cloud Models",
      "The engine communicates through a single provider contract, allowing instant switching between offline and cloud models.")
hub = card(s, 200, 106, 320, 52, CARD2, BLUE)
tb(s, "BaseProvider  (core/providers/base.py)", 210, 110, 300, 20, 12, WHITE, True, align="center")
tb(s, "chat_stream · list_models · test_connection · estimate_tokens", 210, 130, 300, 18, 8.5, MUTED, False, MONO, "center")
provs = [
    ("Ollama", "LOCAL · OFFLINE", "Streams from /api/chat and detects installed local models automatically.", TEAL),
    ("LM Studio & /v1", "LOCAL OR HOSTED", "Connects to any server implementing the standard /v1 chat protocol.", BLUE),
    ("Google Gemini", "CLOUD API", "Streams over SSE and translates tool schemas into Gemini function declarations.", AMBER),
    ("NVIDIA NIM", "CLOUD · RATE-PACED", "2 s pause between calls · 3 retries on 429/503 · immediate error on retired models.", GREEN),
]
cw, gap = 153, 12
for i, (t, tag, b, col) in enumerate(provs):
    x = 36 + i * (cw + gap)
    c = card(s, x, 196, cw, 124)
    connect(s, hub, c, 2, 0, col, 1.25)
    bar(s, x + 12, 208, 18, 3, col)
    tb(s, t, x + 8, 216, cw - 16, 20, 11.5, WHITE, True)
    tb(s, tag, x + 8, 236, cw - 16, 14, 7.5, col, True, MONO)
    tb(s, b, x + 8, 254, cw - 16, 60, 8.8, MUTED, ls=118)
tb(s, "Settings window verifies connectivity and discovers available models; the header menu switches providers at any time.",
   36, 334, 648, 30, 9.5, TEXT, align="center", valign="MIDDLE", bg=CARD2)

# ── 7 · Memory ─────────────────────────────────────────────────────────────
s = new()
frame(s, 7, "Long-Term Memory (RAG)",
      "Privacy-Preserving Local Memory",
      "All project memory stays in local SQLite — even when using cloud models, sensitive history is never stored in the cloud.")
flow = [
    ("Capture", "after a plan run: goal, discoveries, notes, summary", AMBER),
    ("Local Storage", "saved in data/memory/memory.db per project", BLUE),
    ("Selective Recall", "top 3 matches above 0.25 score per prompt", TEAL),
    ("Prompt Injection", "only relevant snippets added + recall_memory tool", GREEN),
]
cw, gap = 153, 12
for i, (t, b, col) in enumerate(flow):
    x = 36 + i * (cw + gap)
    card(s, x, 106, cw, 78)
    dot(s, i + 1, x + 10, 116, col, 20, 9)
    tb(s, t, x + 36, 114, cw - 44, 24, 11.5, WHITE, True, valign="MIDDLE")
    tb(s, b, x + 8, 142, cw - 16, 38, 8.8, MUTED, ls=115)
    if i < 3:
        line(s, x + cw + 1, 145, gap - 2, 0, DIM, 1.25)
card(s, 36, 198, 400, 168)
tb(s, "Retrieval Scoring Method", 48, 206, 380, 20, 13, WHITE, True)
tb(s, "ALWAYS ACTIVE", 48, 234, 120, 14, 8, TEAL, True, MONO)
tb(s, "Keyword overlap: proportion of query terms present in the stored memory", 48, 248, 376, 30, 9.8, TEXT)
bar(s, 48, 282, 376, 0.75, LINE)
tb(s, "WHEN LOCAL nomic-embed-text IS AVAILABLE (OLLAMA)", 48, 290, 340, 14, 8, BLUE, True, MONO)
tb(s, "0.6 × cosine similarity + 0.4 × keyword overlap", 48, 306, 376, 50, 11, WHITE, True, MONO, valign="MIDDLE", bg=CARD2)
card(s, 448, 198, 236, 168)
tb(s, "Data Privacy & Control", 460, 206, 216, 20, 13, WHITE, True)
tb(s, "• Full history stays on disk, never uploaded to cloud storage\n• Memory window to inspect, search, and delete records\n• Duplicate entries skipped automatically\n• In-memory fallback if disk write is restricted",
   460, 232, 216, 128, 9.5, MUTED, ls=142)

# ── 8 · Safety ─────────────────────────────────────────────────────────────
s = new()
frame(s, 8, "Execution Safety",
      "Workspace Isolation and Human-in-the-Loop Control",
      "Designed for sensitive workspaces where file edits and shell commands require clear oversight.")
cx0, cw, rh = 172, 82, 44
for j, (h, col) in enumerate([("Safe", GREEN), ("Auto", AMBER), ("Strict", RED)]):
    x = cx0 + j * (cw + 6)
    tb(s, h.upper() + (" · DEFAULT" if j == 0 else ""), x, 106, cw, 18, 8, col, True, MONO, "center")
    bar(s, x, 124, cw, 2, col)
rows = [
    ("Read operations", "list · read · find · recall", ["auto", "auto", "ask"]),
    ("Write & shell tools", "write · edit lines · run command", ["ask", "auto", "ask"]),
    ("User prompts", "ask_user clarification tool", ["ask", "ask", "ask"]),
]
for i, (n, d, vals) in enumerate(rows):
    y = 132 + i * (rh + 6)
    tb(s, n, 36, y + 4, 132, 18, 10.5, WHITE, True)
    tb(s, d, 36, y + 22, 132, 18, 8, MUTED, False, MONO)
    for j, v in enumerate(vals):
        x = cx0 + j * (cw + 6)
        col = GREEN if v == "auto" else AMBER
        card(s, x, y, cw, rh, CARD, LINE)
        tb(s, "Automatic" if v == "auto" else "Requires approval", x, y, cw, rh, 9, col, True, SANS, "center", "MIDDLE")
card(s, 36, 290, 400, 76, CARD2, LINE)
tb(s, "Synchronous Approval Queue", 48, 296, 380, 18, 11, WHITE, True)
tb(s, "When approval is required, the worker thread pauses on a queue while the UI displays the tool name and arguments. Clicking Authorize runs the tool; Reject returns a refusal to the model.",
   48, 314, 380, 50, 9.2, MUTED, ls=122)
card(s, 452, 106, 232, 260)
tb(s, "Permanent Safeguards", 464, 114, 210, 20, 13, WHITE, True)
for i, (t, b) in enumerate([("Blocked commands", "rm -rf, mkfs, dd if= are rejected in all modes"),
                            ("Workspace confinement", "reads and line edits must stay inside the project folder"),
                            ("Controlled output folder", "newly created files are written to the output directory"),
                            ("Execution limits", "30 s command timeout and 4,000-character output cap")]):
    y = 144 + i * 54
    bar(s, 464, y + 3, 2, 38, BLUE)
    tb(s, t, 474, y, 200, 18, 10.2, WHITE, True)
    tb(s, b, 474, y + 18, 200, 28, 8.8, MUTED)

# ── 9 · Future ─────────────────────────────────────────────────────────────
s = new()
frame(s, 9, "Future Recommendations",
      "Future Work and Research Directions",
      "Addressing current limitations to further close the capability gap between local and cloud models.")
tb(s, "CURRENT LIMITATION", 36, 104, 220, 14, 8, DIM, True, MONO)
tb(s, "PROPOSED IMPROVEMENT", 330, 104, 220, 14, 8, DIM, True, MONO)
fut = [
    ("Evaluator verdict is informational only", "Trigger automatic subtask retries guided by the evaluator's next_action hint", BLUE),
    ("Subtasks execute strictly in list order", "Enforce the planner's depends_on graph and run independent tasks in parallel", TEAL),
    ("Semantic vectors require Ollama running", "Bundle a built-in local embedding model and full BM25 term weighting", AMBER),
    ("Approval cards display raw arguments", "Render a side-by-side line diff preview before authorizing file edits", PINK),
    ("Launched via Python script (./run_app.py)", "Package as a standalone macOS application bundle for zero-setup deployment", GREEN),
]
for i, (a, b, col) in enumerate(fut):
    y = 122 + i * 49
    card(s, 36, y, 276, 41)
    tb(s, a, 48, y, 260, 41, 10.2, MUTED, valign="MIDDLE")
    line(s, 314, y + 20, 12, 0, col, 1.5)
    card(s, 330, y, 354, 41, CARD2, col)
    tb(s, b, 344, y, 336, 41, 10.2, WHITE, True, valign="MIDDLE")

# ── 10 · Demo ──────────────────────────────────────────────────────────────
s = new()
ops.append({"op": "set-background", "slide": s, "color": BG})
shape(s, 470, -140, 420, 420, BLUE, kind="ELLIPSE", alpha=0.10)
tb(s, "10   LIVE DEMONSTRATION", 36, 22, 300, 18, 9, BLUE, True, MONO)
tb(s, "Application Walkthrough", 36, 42, 600, 44, 30, WHITE, True)
tb(s, "End-to-end demonstration of provider setup, prompt routing, planned execution, and local memory.",
   36, 84, 640, 22, 11.5, MUTED)
demo = [
    ("Model Setup", "Open Settings, test connectivity, and switch between local and cloud models.", "provider verification & switching", BLUE),
    ("Direct Routing", "Submit \"tell me how i can multiply 2 matrices\" as a conceptual query.", "Direct Response badge & instant stream", TEAL),
    ("Planned Execution", "Submit \"build a new REST api service\" with Safe mode active.", "Task Plan card → approval prompt → Authorize", AMBER),
    ("Local Memory Recall", "Inspect stored project entries in Memory and ask a related follow-up.", "\"Recalled N memories\" indicator in chat", GREEN),
]
cw, gap = 153, 12
for i, (t, p, look, col) in enumerate(demo):
    x = 36 + i * (cw + gap)
    card(s, x, 124, cw, 204)
    dot(s, i + 1, x + 12, 138, col, 26, 11)
    tb(s, t, x + 10, 174, cw - 20, 22, 13, WHITE, True)
    tb(s, p, x + 10, 198, cw - 20, 56, 9.2, MUTED, ls=120)
    bar(s, x + 12, 260, cw - 24, 0.75, LINE)
    tb(s, "OBSERVED OUTCOME", x + 10, 266, cw - 20, 14, 7.5, col, True, MONO)
    tb(s, look, x + 10, 282, cw - 20, 40, 9.2, TEXT, True)
tb(s, "Thank you  ·  Questions & Discussion", 36, 348, 500, 26, 14, MUTED, True)
tb(s, "Local Agent", 36, 382, 200, 14, 8, DIM)
tb(s, "10 / 10", W - 136, 382, 100, 14, 8, DIM, False, SANS, "right")

# ── notes ──────────────────────────────────────────────────────────────────
md = open("docs/presentation_notes.md").read()
parts = re.split(r"^## Slide \d+ \([^)]*\)\n", md, flags=re.M)[1:]
for sid, note in zip(slides, parts):
    ops.append({"op": "set-notes", "slide": sid, "text": note.strip()})

json.dump(ops, open("docs/slides_batch.json", "w"), indent=0)
print(len(ops), "ops")
