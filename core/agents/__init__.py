"""
core/agents
───────────
Specialized collaborative multi-agent architecture for Local Agent:
  - CollaborationBus : Structured message passing between specialized agents
  - PlannerAgent     : Requirement checking, workspace discovery, DAG planning & dynamic replanning
  - ExecutorAgent    : Tool-using execution engine with verified cross-subtask context handoff
  - CriticAgent      : Independent verification & critique agent with read-only inspection tools
"""

from core.agents.bus import AgentMessage, CollaborationBus
from core.agents.planner_agent import PlannerAgent
from core.agents.executor_agent import ExecutorAgent
from core.agents.critic_agent import CriticAgent

__all__ = [
    "AgentMessage",
    "CollaborationBus",
    "PlannerAgent",
    "ExecutorAgent",
    "CriticAgent",
]
