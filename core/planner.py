"""
core/planner.py
───────────────
Backward-compatible task decomposition helper backed by PlannerAgent.
"""

from typing import Optional, Dict, Any, List
from core.providers.base import BaseProvider
from core.agents.planner_agent import PlannerAgent, PLANNER_SYSTEM_PROMPT

PLANNER_PROMPT = PLANNER_SYSTEM_PROMPT


def run_planner_pass(
    provider: BaseProvider,
    user_request: str,
    workspace_snapshot: str,
    scratchpad_context: str = "",
    max_subtasks: int = 15,
) -> Optional[Dict[str, Any]]:
    """Decomposes user request into dependency-linked subtasks (stateless wrapper)."""
    agent = PlannerAgent(max_subtasks=max_subtasks, max_discovery_turns=1)
    gen = agent.plan_stream(
        provider=provider,
        user_request=user_request,
        workspace_snapshot=workspace_snapshot,
        scratchpad_context=scratchpad_context,
        enable_discovery_tools=False,
    )
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


def replan_remaining_tasks(
    provider: BaseProvider,
    user_request: str,
    workspace_snapshot: str,
    completed_subtasks: List[Dict[str, Any]],
    trigger_context: str,
    feedback: str,
    bus_log: str = "",
    scratchpad_context: str = "",
    next_id: int = 1,
) -> Optional[Dict[str, Any]]:
    agent = PlannerAgent()
    return agent.replan(
        provider=provider,
        user_request=user_request,
        workspace_snapshot=workspace_snapshot,
        completed_subtasks=completed_subtasks,
        trigger_context=trigger_context,
        feedback=feedback,
        bus_log=bus_log,
        scratchpad_context=scratchpad_context,
        next_id=next_id,
    )
