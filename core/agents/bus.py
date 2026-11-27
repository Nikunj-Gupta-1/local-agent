"""
core/agents/bus.py
──────────────────
Structured inter-agent communication bus and shared collaboration state.
Tracks messages exchanged between PlannerAgent, ExecutorAgent, CriticAgent, and Human.
"""

import datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    message_type: str
    summary: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    def to_event(self) -> Dict[str, Any]:
        return {
            "type": "agent_message",
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "summary": self.summary,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CollaborationBus:
    """In-session message bus recording structured handoffs and critiques across agents."""

    def __init__(self):
        self.messages: List[AgentMessage] = []

    def send(
        self,
        sender: str,
        recipient: str,
        message_type: str,
        summary: str,
        payload: Dict[str, Any] | None = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            summary=summary,
            payload=payload or {},
        )
        self.messages.append(msg)
        return msg

    def messages_for(self, recipient: str, limit: int = 10) -> List[AgentMessage]:
        relevant = [m for m in self.messages if m.recipient in (recipient, "all")]
        return relevant[-limit:]

    def format_recent_log(self, limit: int = 8) -> str:
        if not self.messages:
            return "(no prior agent messages)"
        lines = []
        for m in self.messages[-limit:]:
            lines.append(f"- [{m.sender} -> {m.recipient}] ({m.message_type}): {m.summary}")
        return "\n".join(lines)
