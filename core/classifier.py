"""
core/classifier.py
──────────────────
Lightweight 2-Tier Prompt Intent Classifier.
Determines whether a user prompt requires multi-step autonomous planning (PLAN)
or a direct single response (DIRECT).
"""

import re
from typing import Tuple
from core.providers.base import BaseProvider

# Instant Direct Patterns (0ms latency regex matching)
DIRECT_PATTERNS = [
    # Greetings & Chit-chat
    r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening)|yo|sup)\b",
    r"^(who\s+are\s+you|what\s+can\s+you\s+do|how\s+are\s+you|what\s+is\s+your\s+name)\b",
    r"^(thanks|thank\s+you|ok|okay|bye|goodbye|see\s+ya)\b",

    # Direct Knowledge, Math, Explanations, Q&A
    r"^(what\s+is|what\s+are|define|explain|tell\s+me|describe|how\s+to|how\s+can\s+i)\b",
    r"^(why\s+is|why\s+does|how\s+does|how\s+do\s+i)\b",
    r"^(difference\s+between|compare|contrast|summarize|translate|rewrite|format)\b",
    r"^(write\s+a\s+(poem|story|email|message|haiku|joke))\b",
    r".*\b(multiply|matrices|matrix|calculate|compute|solve|equation|formula)\b.*",
]

# Definite Multi-Step Planning Triggers
PLAN_PATTERNS = [
    r"\b(refactor|rewrite\s+entire|redesign|migrate)\b",
    r"\b(build|implement|create|scaffold)\b.*?\b(app|application|feature|system|service|module|pipeline|project|database)\b",
    r"\b(find\s+and\s+fix|debug\s+and\s+fix|resolve\s+all)\b",
    r"\b(step\s+by\s+step|in\s+stages|phases)\b",
]

CLASSIFIER_PROMPT = """\
Analyze this user prompt for an AI agent:
"{prompt}"

Does this request require multi-step project planning, task decomposition, and code editing (PLAN),
or is it a direct conversational question, math explanation, or single answer (DIRECT)?

Reply with ONLY ONE word: PLAN or DIRECT.
"""


class PromptClassifier:
    def __init__(self, mode: str = "auto"):
        self.mode = mode.lower() if mode else "auto"

    def classify(self, prompt: str, provider: BaseProvider = None) -> Tuple[str, str]:
        """
        Returns (route, reason) where route is 'DIRECT' or 'PLAN'.
        """
        p = prompt.strip()

        if self.mode == "always_plan":
            return "PLAN", "Forced by configuration: always_plan"
        if self.mode == "direct_only":
            return "DIRECT", "Forced by configuration: direct_only"

        # Tier 1: Check multi-step planning patterns first
        for pat in PLAN_PATTERNS:
            if re.search(pat, p, re.IGNORECASE):
                return "PLAN", f"Multi-step engineering task matched pattern: '{pat}'"

        # Tier 1: Check instant direct patterns
        for pat in DIRECT_PATTERNS:
            if re.search(pat, p, re.IGNORECASE):
                return "DIRECT", f"Direct query matched pattern: '{pat}'"

        # Short queries (< 35 chars without action verbs)
        if len(p) < 35 and not any(kw in p.lower() for kw in ["fix", "build", "create", "test", "run", "edit", "write"]):
            return "DIRECT", "Short conversational prompt"

        # Tier 2: Quick Model Classification if available
        if provider:
            try:
                messages = [
                    {"role": "system", "content": "You are a prompt intent classifier. Reply only with PLAN or DIRECT."},
                    {"role": "user", "content": CLASSIFIER_PROMPT.format(prompt=p[:400])},
                ]
                tokens = []
                for chunk in provider.chat_stream(messages, temperature=0.0, tools=None):
                    if chunk.get("type") == "token":
                        tokens.append(chunk.get("content", ""))
                res_text = "".join(tokens).strip().upper()
                if "PLAN" in res_text:
                    return "PLAN", "Model classified as multi-step engineering task"
                return "DIRECT", "Model classified as direct response"
            except Exception:
                pass

        # Default fallback
        return "DIRECT", "Default fallback to direct response"
