"""
tests/test_providers.py
───────────────────────
Unit tests for AI providers.
"""

import unittest
from core.providers import get_provider
from core.providers.ollama_provider import OllamaProvider
from core.providers.gemini_provider import GeminiProvider
from core.providers.nvidia_provider import NvidiaProvider
from core.providers.openai_compatible_provider import OpenAICompatibleProvider


class TestProviders(unittest.TestCase):
    def test_provider_factory(self):
        prov = get_provider("ollama", {"ollama_url": "http://127.0.0.1:11434"})
        self.assertIsInstance(prov, OllamaProvider)

        prov_gemini = get_provider("gemini", {"gemini_api_key": "test_key"})
        self.assertIsInstance(prov_gemini, GeminiProvider)

        prov_nvidia = get_provider("nvidia", {"nvidia_api_key": "test_key"})
        self.assertIsInstance(prov_nvidia, NvidiaProvider)

        prov_lm = get_provider("lmstudio", {"openai_base_url": "http://localhost:1234/v1"})
        self.assertIsInstance(prov_lm, OpenAICompatibleProvider)

    def test_gemini_conversion(self):
        prov = GeminiProvider({"gemini_api_key": "test"})
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "tool", "name": "list_dir", "content": '{"ok": true}'},
        ]
        sys_instruction, contents = prov._convert_messages(messages)
        self.assertEqual(sys_instruction, {"parts": [{"text": "You are a helpful assistant."}]})
        self.assertEqual(len(contents), 3)
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(contents[1]["role"], "model")
        self.assertEqual(contents[2]["role"], "user")
        self.assertIn("functionResponse", contents[2]["parts"][0])

    def test_token_estimation(self):
        prov = OllamaProvider({})
        messages = [
            {"role": "user", "content": "Short test message with ~40 chars total"}
        ]
        tokens = prov.estimate_tokens(messages)
        self.assertGreater(tokens, 0)


if __name__ == "__main__":
    unittest.main()
