"""
core/providers/openai_compatible_provider.py
───────────────────────────────────────────
Generic OpenAI-compatible provider for LM Studio, vLLM, LocalAI, Jan,
OpenRouter, Groq, Together, and custom self-hosted endpoints.
"""

import json
import requests
from typing import Generator, Dict, Any, List, Optional
from core.providers.base import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("openai_base_url", "http://localhost:1234/v1").rstrip("/")
        self.api_key = config.get("openai_api_key", "lm-studio")
        self.model = config.get("model", "local-model")
        self.context_window = config.get("context_window", 16384)

    def test_connection(self) -> Dict[str, Any]:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            r = requests.get(f"{self.url}/models", headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return {
                    "ok": True,
                    "message": f"Connected to OpenAI-compatible endpoint ({len(models)} models available)",
                    "models": models or [self.model],
                }
            return {
                "ok": False,
                "message": f"Endpoint responded with HTTP {r.status_code}",
                "models": [],
            }
        except requests.exceptions.ConnectionError:
            return {
                "ok": False,
                "message": f"Cannot reach endpoint at {self.url}. Ensure server (e.g. LM Studio) is running.",
                "models": [],
            }
        except Exception as e:
            return {"ok": False, "message": f"Connection error: {str(e)}", "models": []}

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
        endpoint = f"{self.url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        full_content = []
        full_thinking = []
        accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}

        try:
            r = requests.post(endpoint, json=payload, headers=headers, stream=True, timeout=300)
            r.raise_for_status()

            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})

                    reasoning = delta.get("reasoning_content") or delta.get("thinking") or ""
                    content = delta.get("content") or ""
                    tc_deltas = delta.get("tool_calls", [])

                    if reasoning:
                        full_thinking.append(reasoning)
                        yield {"type": "thinking", "content": reasoning}

                    if content:
                        full_content.append(content)
                        yield {"type": "token", "content": content}

                    if tc_deltas:
                        for tcd in tc_deltas:
                            idx = tcd.get("index", 0)
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = {
                                    "id": tcd.get("id", f"call_{len(accumulated_tool_calls)}"),
                                    "type": "function",
                                    "function": {
                                        "name": tcd.get("function", {}).get("name", ""),
                                        "arguments": tcd.get("function", {}).get("arguments", ""),
                                    },
                                }
                            else:
                                fn = accumulated_tool_calls[idx]["function"]
                                fn["arguments"] += tcd.get("function", {}).get("arguments", "")
                                if tcd.get("function", {}).get("name"):
                                    fn["name"] = tcd["function"]["name"]

            tool_calls_list = list(accumulated_tool_calls.values())
            for tc in tool_calls_list:
                yield {"type": "tool_call", "tool_call": tc}

            yield {
                "type": "done",
                "content": "".join(full_content),
                "thinking": "".join(full_thinking),
                "tool_calls": tool_calls_list,
            }

        except Exception as e:
            yield {"type": "error", "error": f"OpenAI-compatible endpoint error: {str(e)}"}
