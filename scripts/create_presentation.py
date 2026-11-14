#!/usr/bin/env python3
"""
Builds docs/presentation_deck.pptx (10 slides) + docs/presentation_notes.md.
Every statement on the slides is verified against the code in this repository.

Speakers: Nikunj (1, 2, 10) · Aakarsh (3, 4) · Shayan (5, 6) · Uzair (7, 8) · Team (9)
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn
from lxml import etree

# ── palette ─────────────────────────────────────────────────────────────────
def C(h): return RGBColor.from_string(h)
BG_LIGHT, BG_DARK = C("F5F6FA"), C("0B1020")
INK, MUTED, WHITE = C("0F172A"), C("5B6477"), C("FFFFFF")
CARD, CARD_LINE = C("FFFFFF"), C("DDE1EA")
INDIGO, INDIGO_L = C("4F46E5"), C("E8E7FD")
TEAL, TEAL_L = C("0D9488"), C("D5F3EF")
AMBER, AMBER_L = C("D97706"), C("FDEFD3")
ROSE, ROSE_L = C("E11D48"), C("FDE1E7")
GREEN, GREEN_L = C("16A34A"), C("DCF5E4")
DARK_CARD, DARK_LINE = C("151C34"), C("2A3558")
SOFT = C("A8B3D1")

SANS, MONO = "Arial", "Courier New"
SW, SH = 13.333, 7.5

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(SW), Inches(SH)
BLANK = prs.slide_layouts[6]
NOTES = []


# ── primitives ──────────────────────────────────────────────────────────────
def bg(slide, color):
    f = slide.background.fill
    f.solid(); f.fore_color.rgb = color


def box(slide, x, y, w, h, fill=CARD, line=CARD_LINE, lw=1.0, radius=0.10,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE, dash=False):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = min(0.5, radius / min(w, h) * 1.0)
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid(); s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line; s.line.width = Pt(lw)
        if dash:
            ln = s.line._get_or_add_ln()
            d = etree.SubElement(ln, qn("a:prstDash")); d.set("val", "dash")
    s.shadow.inherit = False
    return s


def _runs(p, spec, size, color, bold, font):
    """spec: str | list of (text, dict) runs"""
    if isinstance(spec, str):
        spec = [(spec, {})]
    for t, o in spec:
        r = p.add_run(); r.text = t
        r.font.name = o.get("font", font)
        r.font.size = Pt(o.get("size", size))
        r.font.bold = o.get("bold", bold)
        r.font.color.rgb = o.get("color", color)


def text(slide, x, y, w, h, paras, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, font=SANS, space=4, margin=0.0, line_spacing=1.08):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(margin)
    tf.vertical_anchor = anchor
    if isinstance(paras, (str, tuple)) or (isinstance(paras, list) and paras and isinstance(paras[0], tuple)):
        paras = [paras]
    for i, spec in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; p.space_after = Pt(space); p.line_spacing = line_spacing
        _runs(p, spec, size, color, bold, font)
    return tb


def label_box(slide, x, y, w, h, title, body=None, fill=CARD, line=CARD_LINE, accent=INDIGO,
              tsize=16, bsize=13, tcolor=None, bcolor=None, align=PP_ALIGN.LEFT, lw=1.0,
              anchor=MSO_ANCHOR.MIDDLE, pad=0.16, dash=False, mono_body=False):
    box(slide, x, y, w, h, fill=fill, line=line, lw=lw, dash=dash)
    paras = [[(title, {"bold": True, "size": tsize, "color": tcolor or accent})]]
    if body:
        for b in ([body] if isinstance(body, str) else body):
            paras.append([(b, {"size": bsize, "color": bcolor or MUTED,
                               "font": MONO if mono_body else SANS})])
    text(slide, x + pad, y + 0.05, w - 2 * pad, h - 0.1, paras, align=align, anchor=anchor, space=3)


def arrow(slide, x1, y1, x2, y2, color=MUTED, w=2.0, dash=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color; c.line.width = Pt(w)
    ln = c.line._get_or_add_ln()
    if dash:
        d = etree.SubElement(ln, qn("a:prstDash")); d.set("val", "dash")
    t = etree.SubElement(ln, qn("a:tailEnd")); t.set("type", "triangle"); t.set("w", "med"); t.set("len", "med")
    return c


def pill(slide, x, y, w, h, label, fill, color=WHITE, size=12):
    box(slide, x, y, w, h, fill=fill, line=None, radius=h / 2)
    text(slide, x, y, w, h, [[(label, {"bold": True, "size": size, "color": color})]],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def circle_num(slide, x, y, d, n, fill=INDIGO, size=15):
    s = box(slide, x, y, d, d, fill=fill, line=None, shape=MSO_SHAPE.OVAL)
    text(slide, x, y, d, d, [[(str(n), {"bold": True, "size": size, "color": WHITE})]],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def header(slide, n, section, who, title, sub=None):
    bg(slide, BG_LIGHT)
    box(slide, 0, 0, SW, 0.12, fill=INDIGO, line=None, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 0.6, 0.38, 6, 0.3, [[(section.upper(), {"bold": True, "size": 12, "color": INDIGO})]])
    pill(slide, SW - 0.6 - 1.7, 0.33, 1.7, 0.36, who, INK, size=12)
    text(slide, 0.6, 0.75, 12.1, 0.8, [[(title, {"bold": True, "size": 30, "color": INK})]],
         anchor=MSO_ANCHOR.TOP)
    if sub:
        text(slide, 0.6, 1.42, 12.1, 0.4, [[(sub, {"size": 16, "color": MUTED})]])
    text(slide, 0.6, 7.05, 6, 0.3, [[("Local Agent", {"size": 11, "color": MUTED})]])
    text(slide, SW - 1.6, 7.05, 1.0, 0.3, [[(f"{n} / 10", {"size": 11, "color": MUTED})]], align=PP_ALIGN.RIGHT)


def notes(slide, who, script):
    slide.notes_slide.notes_text_frame.text = script
    NOTES.append((who, script))


def new(): return prs.slides.add_slide(BLANK)


# ═══════════════════════════════════════════════════════════════════════════
# 1 · TITLE (Nikunj)
# ═══════════════════════════════════════════════════════════════════════════
s = new(); bg(s, BG_DARK)
box(s, 0, 0, 0.35, SH, fill=INDIGO, line=None, shape=MSO_SHAPE.RECTANGLE)
text(s, 1.0, 1.25, 11, 1.4, [[("Local Agent", {"bold": True, "size": 72, "color": WHITE})]])
text(s, 1.0, 2.75, 11.3, 1.0,
     [[("A desktop AI coding agent that works with any model, local or cloud", {"size": 26, "color": SOFT})]])
x = 1.0
for label, col in [("Ollama", TEAL), ("LM Studio", INDIGO), ("Google Gemini", AMBER), ("NVIDIA NIM", GREEN)]:
    w = 0.32 + 0.105 * len(label)
    pill(s, x, 3.95, w, 0.42, label, col, size=14); x += w + 0.18

team = [("Nikunj", "Introduction & live demo", INDIGO), ("Aakarsh", "System overview & routing", TEAL),
        ("Shayan", "Planning & models", AMBER), ("Uzair", "Memory & safety", GREEN)]
cw, gap = 2.8, 0.2
for i, (nm, role, col) in enumerate(team):
    cx = 1.0 + i * (cw + gap)
    box(s, cx, 5.35, cw, 1.2, fill=DARK_CARD, line=DARK_LINE)
    box(s, cx, 5.35, 0.09, 1.2, fill=col, line=None, shape=MSO_SHAPE.RECTANGLE)
    text(s, cx + 0.3, 5.5, cw - 0.4, 0.45, [[(nm, {"bold": True, "size": 20, "color": WHITE})]])
    text(s, cx + 0.3, 6.0, cw - 0.4, 0.5, [[(role, {"size": 14, "color": SOFT})]])
notes(s, "Nikunj",
      "Hi everyone, we're presenting Local Agent: a desktop AI coding agent that is not tied to one model. "
      "It can run on a local model through Ollama or LM Studio, or on cloud models through Google Gemini or NVIDIA NIM.\n"
      "I'll explain why we built it, Aakarsh will walk through the architecture and how prompts are routed, "
      "Shayan covers planning and the model layer, and Uzair covers memory and safety. I'll finish with a live demo.")

# ═══════════════════════════════════════════════════════════════════════════
# 2 · WHY (Nikunj)
# ═══════════════════════════════════════════════════════════════════════════
s = new()
header(s, 2, "Introduction", "Nikunj", "Four problems with typical AI coding agents")
rows = [
    ("Everything gets planned", "Even \"hello\" can trigger a slow planning pass with empty task cards.",
     "2-tier router", "Simple questions go straight to the model. Only real engineering tasks get a plan.", INDIGO, INDIGO_L),
    ("Locked to one vendor", "One provider, one API key, no offline option.",
     "Provider layer", "One interface for Ollama, LM Studio, Gemini and NVIDIA NIM. Switch from the header.", TEAL, TEAL_L),
    ("No memory", "Every new session starts from zero.",
     "Local memory", "Findings are saved in a local SQLite file and recalled into future prompts.", AMBER, AMBER_L),
    ("Risky to trust", "An agent that edits files and runs commands can do damage.",
     "Safety modes", "Safe, Auto and Strict modes. Click Authorize or Reject before risky actions run.", GREEN, GREEN_L),
]
text(s, 0.6, 1.55, 5.6, 0.3, [[("THE PROBLEM", {"bold": True, "size": 12, "color": MUTED})]])
text(s, 7.2, 1.55, 5.5, 0.3, [[("WHAT LOCAL AGENT DOES", {"bold": True, "size": 12, "color": MUTED})]])
y0, rh, rg = 1.95, 1.0, 0.16
for i, (pt, pb, st, sb, col, coll) in enumerate(rows):
    y = y0 + i * (rh + rg)
    label_box(s, 0.6, y, 5.9, rh, pt, pb, accent=ROSE, tsize=17, bsize=14)
    arrow(s, 6.55, y + rh / 2, 7.05, y + rh / 2, color=MUTED, w=2.5)
    box(s, 7.1, y, 5.65, rh, fill=coll, line=None)
    box(s, 7.1, y, 0.09, rh, fill=col, line=None, shape=MSO_SHAPE.RECTANGLE)
    text(s, 7.4, y + 0.06, 5.2, rh - 0.1,
         [[(st, {"bold": True, "size": 17, "color": col})], [(sb, {"size": 14, "color": INK})]],
         anchor=MSO_ANCHOR.MIDDLE, space=3)
stats = [("4", "model backends"), ("3", "safety modes"), ("2", "tier prompt router"), ("15", "automated tests")]
for i, (n, l) in enumerate(stats):
    sx = 0.6 + i * 3.07
    box(s, sx, 6.42, 2.9, 0.58, fill=INK, line=None)
    text(s, sx + 0.2, 6.42, 2.6, 0.58,
         [[(n + "  ", {"bold": True, "size": 22, "color": WHITE}), (l, {"size": 14, "color": SOFT})]],
         anchor=MSO_ANCHOR.MIDDLE)
notes(s, "Nikunj",
      "We started from a terminal-only agent script and rebuilt it into a desktop app. These are the four problems we set out to fix.\n"
      "1) Many agents plan everything, even trivial questions. Our router sends simple questions straight to the model.\n"
      "2) Most tools are tied to one vendor. Ours has a single provider interface covering Ollama, LM Studio, Gemini and NVIDIA NIM.\n"
      "3) Agents forget between sessions. We keep a local SQLite memory.\n"
      "4) Agents can edit files and run commands, so we added three safety modes with click-to-approve.\n"
      "The bottom strip is factual: 4 backends, 3 safety modes, a 2-tier router, and 15 automated tests. "
      "Aakarsh will now show how it all fits together.")

# ═══════════════════════════════════════════════════════════════════════════
# 3 · ARCHITECTURE (Aakarsh)
# ═══════════════════════════════════════════════════════════════════════════
s = new()
header(s, 3, "System overview", "Aakarsh", "One engine behind a native desktop window",
       "The engine streams events to the UI, so the window never freezes while the model works")
bw, bh, step = 2.0, 1.25, 2.6
xs = [0.55 + i * step for i in range(5)]
yc = 2.35
label_box(s, xs[0], yc, bw, bh, "Desktop GUI", ["CustomTkinter", "main thread"], accent=INDIGO, align=PP_ALIGN.CENTER)
label_box(s, xs[1], yc, bw, bh, "Engine", ["core/engine.py", "worker thread"], accent=INDIGO, align=PP_ALIGN.CENTER,
          fill=INDIGO_L, line=INDIGO, lw=1.5)
label_box(s, xs[2], yc, bw, bh, "Router", ["core/classifier.py", "DIRECT or PLAN?"], accent=TEAL, align=PP_ALIGN.CENTER)
label_box(s, xs[3], 1.95, bw, 0.95, "Direct path", ["one model call"], accent=TEAL, align=PP_ALIGN.CENTER, bsize=13, tsize=15,
          fill=TEAL_L, line=TEAL)
label_box(s, xs[3], 3.1, bw, 1.0, "Plan path", ["plan, subtasks, check"], accent=AMBER, align=PP_ALIGN.CENTER, bsize=13, tsize=15,
          fill=AMBER_L, line=AMBER)
label_box(s, xs[4], yc, bw, bh, "Providers", ["Ollama · LM Studio", "Gemini · NVIDIA"], accent=GREEN, align=PP_ALIGN.CENTER)
my = yc + bh / 2
arrow(s, xs[0] + bw, my, xs[1], my, color=INDIGO)
arrow(s, xs[1] + bw, my, xs[2], my, color=INDIGO)
arrow(s, xs[2] + bw, my - 0.1, xs[3], 2.42, color=TEAL)
arrow(s, xs[2] + bw, my + 0.1, xs[3], 3.6, color=AMBER)
arrow(s, xs[3] + bw, 2.42, xs[4], my - 0.2, color=TEAL)
arrow(s, xs[3] + bw, 3.6, xs[4], my + 0.25, color=AMBER)
# services under the engine
text(s, 0.55, 4.45, 6, 0.3, [[("THE ENGINE ALSO USES", {"bold": True, "size": 12, "color": MUTED})]])
svc = [("Memory", "SQLite store, recalled into prompts", AMBER),
       ("Tools", "files, shell, scratchpad, recall", TEAL),
       ("Approval gate", "pauses for Authorize / Reject", GREEN)]
for i, (t, b, col) in enumerate(svc):
    sx = 0.55 + i * 4.2
    label_box(s, sx, 4.8, 3.95, 0.85, t, b, accent=col, tsize=16, bsize=14)
    arrow(s, sx + 1.97, 4.8, xs[1] + 1.0, yc + bh, color=CARD_LINE if False else MUTED, w=1.25, dash=True)
# event stream explainer
box(s, 0.55, 5.9, 12.2, 0.95, fill=INK, line=None)
text(s, 0.8, 5.9, 11.7, 0.95, [
    [("The engine is a Python generator. ", {"bold": True, "size": 15, "color": WHITE}),
     ("It yields events like ", {"size": 15, "color": SOFT}),
     ("route_selected, thinking, token, tool_approval_required, tool_result, complete", {"size": 14, "color": WHITE, "font": MONO}),
     (" and the GUI draws each one as it arrives.", {"size": 15, "color": SOFT})]],
     anchor=MSO_ANCHOR.MIDDLE)
text(s, 8.0, 1.5, 4.8, 0.3, [[("Python · CustomTkinter · requests · SQLite", {"size": 12, "color": MUTED})]], align=PP_ALIGN.RIGHT)
notes(s, "Aakarsh",
      "This is the whole system. On the left, the desktop window built with CustomTkinter, which handles only drawing. "
      "The engine in core/engine.py runs on a background worker thread and is written as a Python generator that yields events: "
      "route_selected, thinking, token, tool_approval_required, tool_result and complete. The GUI draws each event as it arrives, so the window never blocks while a model is thinking.\n"
      "A prompt first hits the router. It chooses either the Direct path, which is a single model call, or the Plan path, which plans, runs subtasks and checks them. "
      "Both paths talk to models only through the provider layer.\n"
      "Underneath, the engine uses memory, tools, and the approval gate that pauses when an action needs permission.\n"
      "Honest note for Q&A: the desktop UI code was built with AI assistance; the engine, router, planner, providers, memory and safety logic is our own design.")

# ═══════════════════════════════════════════════════════════════════════════
# 4 · ROUTER (Aakarsh)
# ═══════════════════════════════════════════════════════════════════════════
s = new()
header(s, 4, "Routing", "Aakarsh", "The router checks cheap rules first and asks the model last",
       "Simple questions never reach the planner, so the answer starts streaming immediately")
steps = [
    ("1", "Planning pattern?", "refactor · migrate · build/create … app, service, module · find and fix · step by step", "PLAN", AMBER, AMBER_L),
    ("2", "Direct pattern?", "greetings · what is / explain / how to · compare · summarize · math words", "DIRECT", TEAL, TEAL_L),
    ("3", "Short prompt?", "under 35 characters and none of: fix, build, create, test, run, edit, write", "DIRECT", TEAL, TEAL_L),
    ("4", "Ask the model", "one-word reply, PLAN or DIRECT, at temperature 0. Falls back to DIRECT on any error", "PLAN / DIRECT", INDIGO, INDIGO_L),
]
y0, rh, rg = 1.95, 1.05, 0.22
for i, (n, t, b, res, col, coll) in enumerate(steps):
    y = y0 + i * (rh + rg)
    box(s, 0.6, y, 6.7, rh, fill=CARD, line=CARD_LINE)
    circle_num(s, 0.78, y + 0.27, 0.5, n, fill=INK)
    text(s, 1.5, y + 0.06, 5.7, rh - 0.1,
         [[(t, {"bold": True, "size": 17, "color": INK})], [(b, {"size": 13, "color": MUTED})]],
         anchor=MSO_ANCHOR.MIDDLE, space=2)
    arrow(s, 7.3, y + rh / 2, 7.75, y + rh / 2, color=col, w=2.5)
    pill(s, 7.8, y + rh / 2 - 0.22, 1.55, 0.44, res, col, size=12 if len(res) > 7 else 13)
    if i < 3:
        arrow(s, 3.95, y + rh, 3.95, y + rh + rg, color=MUTED, w=1.75)
text(s, 3.98, y0 + rh + 0.01, 1.5, 0.22, [[("no match", {"size": 11, "color": MUTED})]])
# right panel: examples
px = 9.75
text(s, px, 1.95, 3.2, 0.3, [[("REAL RESULTS", {"bold": True, "size": 12, "color": MUTED})]])
ex = [("hello", "DIRECT", TEAL), ("tell me how i can multiply 2 matrices", "DIRECT", TEAL),
      ("refactor the auth module", "PLAN", AMBER), ("build a new REST api service", "PLAN", AMBER)]
for i, (p, r, col) in enumerate(ex):
    y = 2.3 + i * 0.98
    box(s, px, y, 3.0, 0.86, fill=CARD, line=CARD_LINE)
    text(s, px + 0.15, y + 0.05, 2.7, 0.55, [[("\"" + p + "\"", {"size": 12, "font": MONO, "color": INK})]],
         anchor=MSO_ANCHOR.MIDDLE)
    pill(s, px + 0.15, y + 0.56, 0.95, 0.24, r, col, size=10)
box(s, px, 6.25, 3.0, 0.7, fill=INDIGO_L, line=None)
text(s, px + 0.15, 6.25, 2.75, 0.7,
     [[("Tools still work on the direct path (up to 5 turns). ", {"size": 12, "color": INK})]],
     anchor=MSO_ANCHOR.MIDDLE)
notes(s, "Aakarsh",
      "The router lives in core/classifier.py. It works from cheapest to most expensive.\n"
      "Step 1 checks planning patterns first: words like refactor, migrate, build or create combined with app, service or module, find and fix, step by step. A match means PLAN.\n"
      "Step 2 checks direct patterns: greetings, what is, explain, how to, compare, summarize, and math words. A match means DIRECT.\n"
      "Step 3: a short prompt under 35 characters without action verbs is DIRECT.\n"
      "Step 4, only if nothing matched, we ask the model to reply with a single word, PLAN or DIRECT, at temperature 0. If the model is unavailable or errors, we default to DIRECT.\n"
      "The results on the right are real outputs from our classifier. The user can also force always_plan or direct_only in config.\n"
      "Why it matters: before this, even 'hello' went into planning and the UI showed an empty task plan card with no answer. Now direct questions skip the planner and answer immediately. "
      "On the direct path, tools are still available for up to 5 turns.")

# ═══════════════════════════════════════════════════════════════════════════
# 5 · PLAN PATH (Shayan)
# ═══════════════════════════════════════════════════════════════════════════
s = new()
header(s, 5, "Planning", "Shayan", "The plan path: break the task down, do each piece, check it",
       "Runs only for prompts the router marks as PLAN")
cols = [
    ("1", "Planner", "core/planner.py", "Sees the workspace file list and past session notes. Asks the model for JSON: complexity plus ordered subtasks.", INDIGO),
    ("2", "Subtask loop", "core/engine.py", "Each subtask gets its own conversation: up to 10 model turns, calling tools as needed.", TEAL),
    ("3", "Evaluator", "core/evaluator.py", "Model judges whether the subtask made meaningful progress. Verdict and reason appear in the UI.", AMBER),
    ("4", "Scratchpad", "scratchpad.md", "A markdown file of the goal, files touched, discoveries and done subtasks. Added to every prompt.", ROSE),
    ("5", "Memory save", "core/memory/", "When the run finishes, discoveries, notes and the solution summary are saved to long-term memory.", GREEN),
]
cw, gap, y, ch = 2.28, 0.2, 2.05, 3.2
for i, (n, t, f, b, col) in enumerate(cols):
    x = 0.6 + i * (cw + gap)
    box(s, x, y, cw, ch, fill=CARD, line=CARD_LINE)
    box(s, x, y, cw, 0.1, fill=col, line=None, shape=MSO_SHAPE.RECTANGLE)
    circle_num(s, x + 0.2, y + 0.3, 0.5, n, fill=col)
    text(s, x + 0.2, y + 0.9, cw - 0.4, 0.4, [[(t, {"bold": True, "size": 18, "color": INK})]])
    text(s, x + 0.2, y + 1.3, cw - 0.4, 0.3, [[(f, {"size": 11, "font": MONO, "color": col})]])
    text(s, x + 0.2, y + 1.68, cw - 0.38, 1.5, [[(b, {"size": 13, "color": MUTED})]])
    if i < 4:
        arrow(s, x + cw + 0.01, y + ch / 2, x + cw + gap - 0.01, y + ch / 2, color=MUTED, w=2.25)
text(s, 0.6, 5.5, 8, 0.3, [[("BUILT TO SURVIVE MESSY MODEL OUTPUT", {"bold": True, "size": 12, "color": MUTED})]])
rob = [("JSON pulled out by regex", "Works even when a model wraps its plan in extra text."),
       ("Planner fails?", "Falls back to a single subtask: the user's own request."),
       ("Evaluator unreadable?", "Assumes the subtask is done instead of stalling.")]
for i, (t, b) in enumerate(rob):
    x = 0.6 + i * 4.1
    label_box(s, x, 5.85, 3.95, 1.0, t, b, accent=INK, tsize=15, bsize=13)
notes(s, "Shayan",
      "When the router says PLAN, this pipeline runs.\n"
      "1) The planner in core/planner.py sends the model the workspace file listing plus what has already been done this session, and asks for JSON: a complexity estimate and an ordered list of subtasks, each with a title and scope.\n"
      "2) The engine runs each subtask in its own conversation, up to 10 model turns, with tools like read file, edit lines, run command.\n"
      "3) After each subtask, the evaluator asks the model whether meaningful progress was made. We deliberately made it practical, not pedantic. Right now its verdict is shown in the UI and the run continues; it does not force a retry. That is on our future work list.\n"
      "4) The scratchpad is a markdown file with the goal, files touched, discoveries and completed subtasks, and it is injected into every system prompt so the agent keeps its place.\n"
      "5) At the end, discoveries and the solution summary go into long-term memory, which Uzair covers.\n"
      "Robustness: we extract JSON with a regex, fall back to a single-subtask plan if planning fails, and assume 'done' if the evaluator's reply can't be parsed.")

# ═══════════════════════════════════════════════════════════════════════════
# 6 · PROVIDERS (Shayan)
# ═══════════════════════════════════════════════════════════════════════════
s = new()
header(s, 6, "Models", "Shayan", "One interface, four model backends",
       "The engine never knows which model is answering")
label_box(s, 3.2, 1.95, 6.9, 1.05, "BaseProvider  (core/providers/base.py)",
          "chat_stream · list_models · test_connection · estimate_tokens", accent=INDIGO, fill=INDIGO_L, line=INDIGO,
          lw=1.5, align=PP_ALIGN.CENTER, tsize=17, bsize=14)
provs = [
    ("Ollama", "Local", "Streams from /api/chat. Lists installed models automatically. Default 127.0.0.1:11434.", TEAL),
    ("LM Studio / OpenAI-compatible", "Local or hosted", "Any server speaking the /v1 chat API. Default localhost:1234/v1.", INDIGO),
    ("Google Gemini", "Cloud", "Streams over SSE. Tool schemas are translated to Gemini function declarations.", AMBER),
    ("NVIDIA NIM", "Cloud, free tier", "2 s pause between calls. On 429 / 503: up to 3 retries with doubling wait. Other 4xx fail fast with a clear message.", GREEN),
]
cw, gap, y, ch = 2.95, 0.133, 3.45, 2.65
for i, (t, tag, b, col) in enumerate(provs):
    x = 0.6 + i * (cw + gap)
    arrow(s, 6.65, 3.0, x + cw / 2, y, color=col, w=2.0)
    box(s, x, y, cw, ch, fill=CARD, line=CARD_LINE)
    box(s, x, y, cw, 0.1, fill=col, line=None, shape=MSO_SHAPE.RECTANGLE)
    text(s, x + 0.2, y + 0.25, cw - 0.4, 0.65, [[(t, {"bold": True, "size": 16, "color": INK})]])
    pill(s, x + 0.2, y + 0.92, 1.55 if len(tag) > 8 else 0.95, 0.28, tag, col, size=10)
    text(s, x + 0.2, y + 1.3, cw - 0.4, 1.3, [[(b, {"size": 13, "color": MUTED})]])
box(s, 0.6, 6.3, 12.2, 0.6, fill=INK, line=None)
text(s, 0.85, 6.3, 11.7, 0.6,
     [[("Settings screen: ", {"bold": True, "size": 14, "color": WHITE}),
       ("enter a URL or key, press Test Connection, pick a model. The header dropdown switches provider anytime.",
        {"size": 14, "color": SOFT})]], anchor=MSO_ANCHOR.MIDDLE)
notes(s, "Shayan",
      "Every backend implements the same abstract class, BaseProvider: chat_stream, list_models, test_connection and estimate_tokens. "
      "The engine and GUI only talk to that interface, so adding a backend does not touch the rest of the app.\n"
      "Ollama is fully local and we list installed models automatically. LM Studio and any other server that speaks the OpenAI-style /v1 API use the same compatible provider. "
      "Gemini streams over server-sent events and we translate our tool definitions into Gemini function declarations.\n"
      "NVIDIA NIM's free tier is rate limited, so we pause 2 seconds between calls, retry up to 3 times with a doubling wait on 429 or 503, "
      "and fail immediately with a clear message on other client errors. That last part came from a real bug: a retired model returned HTTP 410 and the app just hung. "
      "Now the user sees an error card telling them what is wrong.\n"
      "In the Settings screen you enter a key or URL, press Test Connection, and pick a model.")

# ═══════════════════════════════════════════════════════════════════════════
# 7 · MEMORY (Uzair)
# ═══════════════════════════════════════════════════════════════════════════
s = new()
header(s, 7, "Memory", "Uzair", "Long-term memory that stays on your machine",
       "A local SQLite file, no cloud database, no extra service to run")
flow = [("Harvest", "After a plan run: goal, discoveries, notes, solution summary", AMBER),
        ("Store", "data/memory/memory.db, scoped per project", INDIGO),
        ("Recall", "Next prompt: top 3 matches above score 0.25", TEAL),
        ("Inject", "Added to the system prompt. The model can also call recall_memory", GREEN)]
cw, gap, y, ch = 2.85, 0.267, 2.0, 1.75
for i, (t, b, col) in enumerate(flow):
    x = 0.6 + i * (cw + gap)
    box(s, x, y, cw, ch, fill=CARD, line=CARD_LINE)
    box(s, x, y, cw, 0.1, fill=col, line=None, shape=MSO_SHAPE.RECTANGLE)
    circle_num(s, x + 0.18, y + 0.28, 0.42, i + 1, fill=col, size=13)
    text(s, x + 0.72, y + 0.28, cw - 0.9, 0.42, [[(t, {"bold": True, "size": 18, "color": INK})]], anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.2, y + 0.85, cw - 0.4, 0.85, [[(b, {"size": 13, "color": MUTED})]])
    if i < 3:
        arrow(s, x + cw + 0.01, y + ch / 2, x + cw + gap - 0.01, y + ch / 2, color=MUTED, w=2.25)
# scoring card
box(s, 0.6, 4.05, 7.1, 2.85, fill=CARD, line=CARD_LINE)
text(s, 0.85, 4.15, 6.6, 0.4, [[("How a memory is scored", {"bold": True, "size": 18, "color": INK})]])
box(s, 0.85, 4.7, 6.6, 0.8, fill=TEAL_L, line=None)
text(s, 1.05, 4.7, 6.3, 0.8, [[("Always:  ", {"bold": True, "size": 14, "color": TEAL}),
                               ("keyword overlap, the share of query words found in the memory", {"size": 14, "color": INK})]],
     anchor=MSO_ANCHOR.MIDDLE)
box(s, 0.85, 5.6, 6.6, 1.15, fill=INDIGO_L, line=None)
text(s, 1.05, 5.6, 6.3, 1.15, [
    [("If Ollama has nomic-embed-text:", {"bold": True, "size": 14, "color": INDIGO})],
    [("score = 0.6 × embedding cosine + 0.4 × keyword overlap", {"size": 14, "font": MONO, "color": INK})]],
    anchor=MSO_ANCHOR.MIDDLE, space=4)
# control card
box(s, 7.95, 4.05, 4.8, 2.85, fill=CARD, line=CARD_LINE)
text(s, 8.2, 4.15, 4.3, 0.4, [[("You stay in control", {"bold": True, "size": 18, "color": INK})]])
text(s, 8.2, 4.7, 4.35, 2.15, [
    [("Memory window lists, searches and deletes entries", {"size": 14, "color": MUTED})],
    [("Exact duplicates are skipped", {"size": 14, "color": MUTED})],
    [("Chat shows \"Recalled N memories\" when any are used", {"size": 14, "color": MUTED})],
    [("If the database cannot open, it falls back to memory in RAM", {"size": 14, "color": MUTED})]], space=7)
notes(s, "Uzair",
      "Without memory, an agent forgets everything when you close it. Ours keeps a local SQLite file at data/memory/memory.db. Nothing is sent anywhere.\n"
      "1) Harvest: when a plan run finishes, we save the goal, discoveries, notes and a summary of the solution.\n"
      "2) Store: entries are tagged to the project folder.\n"
      "3) Recall: on the next prompt we look up the top 3 matches above a 0.25 score.\n"
      "4) Inject: matches are added to the system prompt, and the model can also call a recall_memory tool.\n"
      "Scoring, stated precisely: keyword overlap is always computed, meaning the fraction of query words found in the memory. "
      "If a local Ollama embedding model, nomic-embed-text, is available, the score becomes 0.6 times embedding cosine similarity plus 0.4 times keyword overlap. "
      "Without it, it is keyword overlap only. Semantic search is an optional upgrade, not a requirement.\n"
      "Users can open the Memory window to list, search and delete memories. Currently we save memories after plan runs only.")

# ═══════════════════════════════════════════════════════════════════════════
# 8 · SAFETY (Uzair)
# ═══════════════════════════════════════════════════════════════════════════
s = new()
header(s, 8, "Safety", "Uzair", "You choose how much the agent may do on its own",
       "Switch mode from the header at any time. The default is Safe")
tx, ty = 0.6, 1.95
c0, cw, rh = 3.2, 1.85, 0.78
hdrs = [("Safe", "default", GREEN), ("Auto", "", AMBER), ("Strict", "", ROSE)]
for j, (h, sub, col) in enumerate(hdrs):
    x = tx + c0 + j * (cw + 0.1)
    box(s, x, ty, cw, 0.62, fill=col, line=None)
    text(s, x, ty, cw, 0.62, [[(h + (" (default)" if sub else ""), {"bold": True, "size": 15, "color": WHITE})]],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
table = [
    ("Read tools", "list, read, find, stat, recall", ["auto", "auto", "ask"]),
    ("Change tools", "write_file, edit_file_lines, run_command", ["ask", "auto", "ask"]),
    ("Questions to you", "ask_user", ["ask", "ask", "ask"]),
]
for i, (n, d, vals) in enumerate(table):
    y = ty + 0.72 + i * (rh + 0.1)
    box(s, tx, y, c0 - 0.1, rh, fill=CARD, line=CARD_LINE)
    text(s, tx + 0.15, y, c0 - 0.35, rh,
         [[(n, {"bold": True, "size": 15, "color": INK})], [(d, {"size": 11, "color": MUTED, "font": MONO})]],
         anchor=MSO_ANCHOR.MIDDLE, space=1)
    for j, v in enumerate(vals):
        x = tx + c0 + j * (cw + 0.1)
        fill, col, lab = (GREEN_L, GREEN, "Runs automatically") if v == "auto" else (AMBER_L, AMBER, "Asks first")
        box(s, x, y, cw, rh, fill=fill, line=None)
        text(s, x, y, cw, rh, [[(lab, {"bold": True, "size": 13, "color": col})]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
# approval mechanism
box(s, 0.6, 5.2, 7.35, 1.7, fill=INK, line=None)
text(s, 0.85, 5.3, 6.9, 1.5, [
    [("How \"asks first\" works", {"bold": True, "size": 16, "color": WHITE})],
    [("The engine thread blocks on a queue. The GUI shows a card with the tool name and its arguments. "
      "Click Authorize and the action runs; click Reject and the model is told it was refused.", {"size": 13, "color": SOFT})]],
     anchor=MSO_ANCHOR.MIDDLE, space=6)
# guard rails
box(s, 8.2, 1.95, 4.55, 4.95, fill=CARD, line=CARD_LINE)
text(s, 8.45, 2.05, 4.1, 0.4, [[("Always-on guard rails", {"bold": True, "size": 18, "color": INK})]])
gr = [("Blocked commands", "rm -rf, mkfs, dd if= and others from config never run, even in Auto"),
      ("Workspace only", "File reads and line edits must stay inside the chosen folder"),
      ("Output folder", "New files are written to the configured output folder"),
      ("Command limits", "30 s timeout and capped output")]
for i, (t, b) in enumerate(gr):
    y = 2.6 + i * 1.07
    box(s, 8.45, y + 0.06, 0.08, 0.85, fill=INDIGO, line=None, shape=MSO_SHAPE.RECTANGLE)
    text(s, 8.7, y, 3.95, 1.0, [[(t, {"bold": True, "size": 14, "color": INK})], [(b, {"size": 12, "color": MUTED})]],
         anchor=MSO_ANCHOR.MIDDLE, space=2)
notes(s, "Uzair",
      "An agent that can write files and run shell commands needs limits. We have three modes you can switch from the header at any time.\n"
      "Safe is the default: read tools run automatically, but write_file, edit_file_lines and run_command ask first.\n"
      "Auto lets all tools run without asking, which is fast but you are trusting the model. The guard rails on the right still apply.\n"
      "Strict asks before every tool call, including reads.\n"
      "In every mode, the ask_user tool, where the model asks you a question, waits for your answer.\n"
      "Under the hood, when approval is needed the engine thread blocks on a queue. The GUI shows a card with the tool name and arguments. "
      "Authorize runs it; Reject sends the model a message that it was refused.\n"
      "Guard rails that always apply: a configurable blocked-command list (for example rm -rf, mkfs, dd if=) that never runs even in Auto; "
      "reads and line edits restricted to the chosen workspace folder; new files go to the output folder; commands time out at 30 seconds with capped output.\n"
      "Be upfront in Q&A: Auto mode really does not ask, and the approval card shows arguments rather than a diff. A diff preview is on our future work list.")

# ═══════════════════════════════════════════════════════════════════════════
# 9 · FUTURE (Team)
# ═══════════════════════════════════════════════════════════════════════════
s = new()
header(s, 9, "Future recommendations", "Team", "What we would build next",
       "Each item closes a limitation we found in the current version")
fut = [
    ("Evaluator is advisory", "Retry a subtask automatically when the evaluator says it is not done, using its next_action hint.", INDIGO),
    ("Subtasks run in list order", "Use the planner's depends_on field to order work and run independent subtasks in parallel.", TEAL),
    ("Semantic memory needs Ollama", "Ship a built-in embedding fallback and proper BM25 ranking for keyword matching.", AMBER),
    ("Approval cards show raw arguments", "Show a file diff preview before you authorize an edit.", GREEN),
    ("Starts with ./run_app.py", "Package it as a double-click macOS app so setup is not needed.", ROSE),
]
text(s, 0.6, 1.9, 5, 0.3, [[("TODAY", {"bold": True, "size": 12, "color": MUTED})]])
text(s, 6.95, 1.9, 5, 0.3, [[("NEXT", {"bold": True, "size": 12, "color": MUTED})]])
y0, rh, rg = 2.25, 0.82, 0.14
for i, (a, b, col) in enumerate(fut):
    y = y0 + i * (rh + rg)
    label_box(s, 0.6, y, 5.9, rh, a, None, accent=INK, tsize=16)
    arrow(s, 6.55, y + rh / 2, 6.85, y + rh / 2, color=col, w=2.5)
    box(s, 6.9, y, 5.85, rh, fill=CARD, line=col, lw=1.5)
    box(s, 6.9, y, 0.09, rh, fill=col, line=None, shape=MSO_SHAPE.RECTANGLE)
    text(s, 7.2, y, 5.45, rh, [[(b, {"size": 14, "color": INK})]], anchor=MSO_ANCHOR.MIDDLE)
notes(s, "Team",
      "These next steps come straight from limitations we found while building. "
      "First, the evaluator currently only reports; making it trigger a retry is the natural next step. "
      "Second, the planner already outputs dependencies between subtasks, but we run them in order; we could honour dependencies and parallelise independent ones. "
      "Third, semantic memory needs an Ollama embedding model; a built-in fallback and real BM25 would make it work everywhere. "
      "Fourth, approval cards show raw arguments; a diff preview would make decisions easier. "
      "Fifth, packaging as a double-click macOS app. Now Nikunj will show it running.")

# ═══════════════════════════════════════════════════════════════════════════
# 10 · DEMO (Nikunj)
# ═══════════════════════════════════════════════════════════════════════════
s = new(); bg(s, BG_DARK)
box(s, 0, 0, 0.35, SH, fill=INDIGO, line=None, shape=MSO_SHAPE.RECTANGLE)
pill(s, SW - 0.6 - 1.7, 0.33, 1.7, 0.36, "Nikunj", INDIGO, size=12)
text(s, 1.0, 0.45, 8, 0.3, [[("LIVE DEMO", {"bold": True, "size": 13, "color": INDIGO})]])
text(s, 1.0, 0.85, 11.5, 0.9, [[("Let's run it", {"bold": True, "size": 44, "color": WHITE})]])
demo = [
    ("Pick a model", "Open Settings, press Test Connection, choose a provider and model in the header.",
     "Setup screen and provider switching", INDIGO),
    ("Ask a simple question", "\"tell me how i can multiply 2 matrices\"",
     "Direct Response Mode badge, answer streams, no plan card", TEAL),
    ("Give it a real task", "\"build a new REST api service\"  (Safe mode)",
     "Task Plan card, then an approval card. Click Authorize.", AMBER),
    ("Check memory", "Open Memory, then ask a related follow-up.",
     "Saved entries, and \"Recalled N memories\" in chat", GREEN),
]
cw, gap, y, ch = 2.85, 0.2, 2.2, 3.7
for i, (t, p, w, col) in enumerate(demo):
    x = 1.0 + i * (cw + gap)
    box(s, x, y, cw, ch, fill=DARK_CARD, line=DARK_LINE)
    box(s, x, y, cw, 0.1, fill=col, line=None, shape=MSO_SHAPE.RECTANGLE)
    circle_num(s, x + 0.25, y + 0.35, 0.55, i + 1, fill=col, size=16)
    text(s, x + 0.25, y + 1.05, cw - 0.5, 0.75, [[(t, {"bold": True, "size": 19, "color": WHITE})]])
    text(s, x + 0.25, y + 1.75, cw - 0.5, 0.95, [[(p, {"size": 13, "color": SOFT})]])
    box(s, x + 0.2, y + 2.7, cw - 0.4, 0.82, fill=BG_DARK, line=None)
    text(s, x + 0.32, y + 2.7, cw - 0.64, 0.82, [[("Look for: ", {"bold": True, "size": 12, "color": col}),
                                                  (w, {"size": 12, "color": WHITE})]], anchor=MSO_ANCHOR.MIDDLE)
text(s, 1.0, 6.35, 11.5, 0.4, [[("Start with ./run_app.py   ·   Questions?", {"size": 15, "color": SOFT})]])
notes(s, "Nikunj",
      "Demo run sheet, in order:\n"
      "1) Open Settings, press Test Connection on a provider, then pick the provider and model in the header.\n"
      "2) Ask 'tell me how i can multiply 2 matrices'. You'll see the Direct Response Mode badge and the answer streams with no plan card.\n"
      "3) With Safe mode on, ask 'build a new REST api service'. You'll see the Task Plan card, then an approval card when it wants to write a file. Click Authorize. Then the evaluator verdict appears per subtask.\n"
      "4) Open the Memory window to show what was saved, then ask a related follow-up to show 'Recalled N memories'.\n"
      "Before presenting: start with ./run_app.py, confirm your API key or local model works, and keep a backup provider selected in case of rate limits.")

# ── save ────────────────────────────────────────────────────────────────────
os.makedirs("docs", exist_ok=True)
prs.save("docs/presentation_deck.pptx")
with open("docs/presentation_notes.md", "w") as f:
    f.write("# Local Agent: speaker notes\n\n")
    for i, (who, script) in enumerate(NOTES, 1):
        f.write(f"## Slide {i} ({who})\n\n{script}\n\n")
print("saved docs/presentation_deck.pptx")
