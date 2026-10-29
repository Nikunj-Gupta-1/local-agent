"""
core/providers/base.py
──────────────────────
Abstract Base Provider interface for all LLM backends.
"""

from abc import ABC, abstractmethod
from typing import Generator, Dict, Any, List, Optional
import json

class BaseProvider(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
        enable_thinking: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Yields chunk dictionaries:
          {"type": "token", "content": str}
          {"type": "thinking", "content": str}
          {"type": "tool_call", "tool_call": dict}
          {"type": "done", "content": str, "thinking": str, "tool_calls": list}
        """
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        """Fetch available models from the provider endpoint."""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Test endpoint reachability and credentials.
        Returns: {"ok": bool, "message": str, "models": list[str]}
        """
        pass

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Rough token estimate (~3 characters per token)."""
        total_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
        return max(1, total_chars // 3)
