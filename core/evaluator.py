"""
core/evaluator.py
─────────────────
Backward-compatible completion evaluation helper backed by CriticAgent.
"""

from typing import Dict, Any, List
from core.providers.base import BaseProvider
from core.agents.critic_agent import CriticAgent, CRITIC_PROMPT

EVALUATOR_PROMPT = CRITIC_PROMPT


def check_satisfaction(
    provider: BaseProvider,
    subtask: Dict[str, Any],
    last_response: str,
    tool_history: List[Dict[str, Any]],
    original_request: str = "",
    temperature: float = 0.1,
) -> Dict[str, Any]:
    """Evaluates whether a sub-task has been satisfactorily completed."""
    critic = CriticAgent(temperature=temperature, max_verify_turns=1)
    report = {
        "subtask_id": subtask.get("id"),
        "last_response": last_response,
        "tool_records": tool_history,
        "evidence_snippets": [],
    }
    gen = critic.evaluate_stream(
        provider=provider,
        subtask=subtask,
        report=report,
        original_request=original_request,
        tool_runner=None,
    )
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value
