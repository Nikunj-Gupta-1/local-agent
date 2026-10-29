"""
core/providers/__init__.py
──────────────────────────
Provider factory and registry.
"""

from typing import Dict, Any
from core.providers.base import BaseProvider
from core.providers.ollama_provider import OllamaProvider
from core.providers.nvidia_provider import NvidiaProvider
from core.providers.gemini_provider import GeminiProvider
from core.providers.openai_compatible_provider import OpenAICompatibleProvider

PROVIDER_REGISTRY = {
    "ollama": OllamaProvider,
    "nvidia": NvidiaProvider,
    "gemini": GeminiProvider,
    "lmstudio": OpenAICompatibleProvider,
    "openai_compatible": OpenAICompatibleProvider,
}


def get_provider(provider_name: str, config: Dict[str, Any]) -> BaseProvider:
    name = (provider_name or "ollama").lower()
    provider_cls = PROVIDER_REGISTRY.get(name, OllamaProvider)
    return provider_cls(config)
