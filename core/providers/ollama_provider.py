"""
core/providers/ollama_provider.py
─────────────────────────────────
Ollama local / remote provider with streaming, thinking token parsing,
tool calling, and dynamic model discovery.
"""

import json
import requests
from typing import Generator, Dict, Any, List, Optional
from core.providers.base import BaseProvider


class OllamaProvider(BaseProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("ollama_url", "http://127.0.0.1:11434").rstrip("/")
        self.model = config.get("model", "gemma4-e4b-64k:latest")
        self.context_window = config.get("context_window", 65536)

    def test_connection(self) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            return {
                "ok": True,
                "message": f"Connected to Ollama ({len(models)} models available)",
                "models": models,
            }
        except requests.exceptions.ConnectionError:
            return {
                "ok": False,
                "message": f"Cannot reach Ollama at {self.url}. Ensure 'ollama serve' is running.",
                "models": [],
            }
        except Exception as e:
            return {
                "ok": False,
                "message": f"Ollama connection error: {str(e)}",
                "models": [],
            }

    def list_models(self) -> List[str]:
        res = self.test_connection()
        return res.get("models", [])

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
        enable_thinking: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        endpoint = f"{self.url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": enable_thinking,
            "options": {
                "num_ctx": self.context_window,
                "temperature": temperature,
                "top_k": 64,
                "top_p": 0.95,
            },
        }
        if tools:
            payload["tools"] = tools

        full_content = []
        full_thinking = []
        accumulated_tool_calls = []

        try:
            r = requests.post(endpoint, json=payload, stream=True, timeout=300)
            r.raise_for_status()

            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue

                msg = chunk.get("message", {})
                content_delta = msg.get("content", "")
                thinking_delta = msg.get("thinking", "")
                tool_calls = msg.get("tool_calls", [])

                if thinking_delta:
                    full_thinking.append(thinking_delta)
                    yield {"type": "thinking", "content": thinking_delta}

                if content_delta:
                    full_content.append(content_delta)
                    yield {"type": "token", "content": content_delta}

                if tool_calls:
                    for tc in tool_calls:
                        accumulated_tool_calls.append(tc)
                        yield {"type": "tool_call", "tool_call": tc}

                if chunk.get("done", False):
                    break

        except Exception as e:
            yield {"type": "error", "error": f"Ollama error: {str(e)}"}
            return

        yield {
            "type": "done",
            "content": "".join(full_content),
            "thinking": "".join(full_thinking),
            "tool_calls": accumulated_tool_calls,
        }
