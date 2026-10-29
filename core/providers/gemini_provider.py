"""
core/providers/gemini_provider.py
─────────────────────────────────
Google Gemini API provider (Gemini 2.5 Flash, Gemini 2.5 Pro, Flash Lite)
with SSE streaming, native function calling, and model discovery.
"""

import json
import requests
from typing import Generator, Dict, Any, List, Optional
from core.providers.base import BaseProvider


class GeminiProvider(BaseProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("gemini_api_key", "")
        self.model = config.get("model", "gemini-2.5-flash")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "message": "Gemini API key is missing.", "models": []}
        try:
            url = f"{self.base_url}/models?key={self.api_key}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                models = [
                    m.get("name", "").replace("models/", "")
                    for m in data.get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]
                return {
                    "ok": True,
                    "message": f"Connected to Google Gemini ({len(models)} models available)",
                    "models": models or ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"],
                }
            elif r.status_code == 400 or r.status_code == 403:
                return {"ok": False, "message": "Invalid Gemini API key", "models": []}
            else:
                return {"ok": False, "message": f"Gemini error HTTP {r.status_code}", "models": []}
        except Exception as e:
            return {"ok": False, "message": f"Cannot reach Gemini API: {str(e)}", "models": []}

    def list_models(self) -> List[str]:
        res = self.test_connection()
        if res.get("ok") and res.get("models"):
            return res["models"]
        return [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.5-flash-lite",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ]

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Convert standard OpenAI-style messages to Gemini format."""
        system_instruction = None
        contents = []

        for m in messages:
            role = m.get("role")
            content = m.get("content", "")

            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            elif role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}],
                })
            elif role == "assistant":
                parts = []
                if content:
                    parts.append({"text": content})
                if m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}
                        parts.append({
                            "functionCall": {
                                "name": fn.get("name"),
                                "args": args,
                            }
                        })
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                tool_name = m.get("name", "tool")
                try:
                    res_obj = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    res_obj = {"result": content}

                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": tool_name,
                            "response": res_obj if isinstance(res_obj, dict) else {"output": res_obj},
                        }
                    }]
                })

        return system_instruction, contents

    def _convert_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Convert OpenAI tool schemas to Gemini function declarations."""
        if not tools:
            return None
        declarations = []
        for t in tools:
            fn = t.get("function", {})
            declarations.append({
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            })
        return [{"functionDeclarations": declarations}]

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
        enable_thinking: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        if not self.api_key:
            yield {"type": "error", "error": "Gemini API key is not configured."}
            return

        model_name = self.model
        if not model_name.startswith("gemini"):
            model_name = "gemini-2.5-flash"

        endpoint = f"{self.base_url}/models/{model_name}:streamGenerateContent?key={self.api_key}&alt=sse"

        system_instruction, contents = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools)

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 16384,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        if gemini_tools:
            payload["tools"] = gemini_tools

        full_content = []
        full_thinking = []
        accumulated_tool_calls = []

        try:
            r = requests.post(endpoint, json=payload, stream=True, timeout=300)
            r.raise_for_status()

            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue

                    candidates = chunk.get("candidates", [])
                    if not candidates:
                        continue
                    candidate = candidates[0]
                    content_obj = candidate.get("content", {})
                    parts = content_obj.get("parts", [])

                    for part in parts:
                        text = part.get("text", "")
                        # Gemini 2.5 thinking tokens or normal text
                        if part.get("thought", False):
                            full_thinking.append(text)
                            yield {"type": "thinking", "content": text}
                        elif text:
                            full_content.append(text)
                            yield {"type": "token", "content": text}

                        if "functionCall" in part:
                            fc = part["functionCall"]
                            tc = {
                                "id": f"call_{fc.get('name')}_{len(accumulated_tool_calls)}",
                                "type": "function",
                                "function": {
                                    "name": fc.get("name"),
                                    "arguments": json.dumps(fc.get("args", {})),
                                },
                            }
                            accumulated_tool_calls.append(tc)
                            yield {"type": "tool_call", "tool_call": tc}

        except Exception as e:
            yield {"type": "error", "error": f"Gemini API error: {str(e)}"}
            return

        yield {
            "type": "done",
            "content": "".join(full_content),
            "thinking": "".join(full_thinking),
            "tool_calls": accumulated_tool_calls,
        }
