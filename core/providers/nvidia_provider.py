"""
core/providers/nvidia_provider.py
─────────────────────────────────
NVIDIA NIM Cloud Provider with rate pacing for the free tier,
exponential backoff on rate limits, fast failure on client errors,
and reasoning extraction.
"""

import time
import json
import requests
from typing import Generator, Dict, Any, List, Optional
from core.providers.base import BaseProvider


class NvidiaProvider(BaseProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("nvidia_url", "https://integrate.api.nvidia.com/v1").rstrip("/")
        self.api_key = config.get("nvidia_api_key", "")
        self.model = config.get("model", "nvidia/nemotron-3-ultra-550b-a55b")
        self.pace_delay = float(config.get("nvidia_pace_delay", 2.0))

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "message": "NVIDIA API Key is missing.", "models": []}
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            # Test model endpoint with a minimal query to verify active deployment
            test_payload = {
                "model": self.model or "nvidia/nemotron-3-ultra-550b-a55b",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }
            r = requests.post(f"{self.url}/chat/completions", headers=headers, json=test_payload, timeout=8)
            if r.status_code == 200:
                return {
                    "ok": True,
                    "message": f"NVIDIA NIM connected successfully (Model: {self.model})",
                    "models": [self.model, "nvidia/nemotron-3-ultra-550b-a55b"],
                }
            elif r.status_code == 410:
                return {"ok": False, "message": f"Model '{self.model}' is deprecated/retired (HTTP 410 Gone). Please switch to 'nvidia/nemotron-3-ultra-550b-a55b'.", "models": []}
            elif r.status_code == 401:
                return {"ok": False, "message": "Invalid NVIDIA API key (HTTP 401 Unauthorized)", "models": []}
            else:
                return {"ok": False, "message": f"NVIDIA NIM HTTP {r.status_code}: {r.text[:120]}", "models": []}
        except Exception as e:
            return {"ok": False, "message": f"Cannot reach NVIDIA NIM: {str(e)}", "models": []}

    def list_models(self) -> List[str]:
        return [
            "nvidia/nemotron-3-ultra-550b-a55b",
        ]

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
        enable_thinking: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        if not self.api_key:
            yield {"type": "error", "error": "NVIDIA API Key not provided. Please enter your key in Settings."}
            return

        endpoint = f"{self.url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.95,
            "max_tokens": 8192,
            "stream": True,
        }

        # Pacing for NVIDIA NIM Free Tier
        if self.pace_delay > 0:
            time.sleep(self.pace_delay)

        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            if attempt > 0:
                time.sleep(retry_delay)
                retry_delay *= 2

            try:
                r = requests.post(endpoint, json=payload, headers=headers, stream=True, timeout=60)

                # Rate limiting or temporary service unavailable: retry
                if r.status_code in (429, 503):
                    yield {"type": "status", "message": f"NVIDIA rate limit (HTTP {r.status_code}). Pacing retry in {retry_delay:.1f}s..."}
                    continue

                # Client errors (400, 401, 404, 410): Fail immediately with clear explanation
                if r.status_code >= 400 and r.status_code < 500:
                    err_text = r.text
                    try:
                        err_json = r.json()
                        err_text = err_json.get("detail") or err_json.get("message") or err_text
                    except Exception:
                        pass

                    if r.status_code == 410:
                        yield {"type": "error", "error": f"[NVIDIA NIM HTTP 410] The model '{self.model}' has reached end-of-life and is retired. Please switch to 'nvidia/nemotron-3-ultra-550b-a55b' in the header dropdown."}
                    elif r.status_code == 401:
                        yield {"type": "error", "error": "[NVIDIA NIM HTTP 401] Invalid or expired NVIDIA API Key. Please check your key in Settings."}
                    elif r.status_code == 404:
                        yield {"type": "error", "error": f"[NVIDIA NIM HTTP 404] Model '{self.model}' not found on this account. Please select an active model in the header."}
                    else:
                        yield {"type": "error", "error": f"[NVIDIA NIM HTTP {r.status_code}] {err_text[:250]}"}
                    return

                r.raise_for_status()

                full_content = []
                full_thinking = []
                accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}

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
                return

            except Exception as e:
                if attempt == max_retries - 1:
                    yield {"type": "error", "error": f"NVIDIA NIM connection error: {str(e)}"}
                    return
