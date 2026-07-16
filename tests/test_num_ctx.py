"""num_ctx comes from profile / local_config and is sent to Ollama."""

from __future__ import annotations

from assistant.config import AssistantConfig, resolve_num_ctx, _PROFILES
from assistant.llm import OllamaClient


def test_profiles_define_num_ctx() -> None:
    for name, profile in _PROFILES.items():
        assert int(profile["num_ctx"]) >= 4096, name


def test_resolve_num_ctx_matches_profile_default() -> None:
    assert resolve_num_ctx("laptop") == 8192
    assert resolve_num_ctx("desktop") == 16384


def test_ollama_options_include_num_ctx() -> None:
    cfg = AssistantConfig(num_ctx=12288)
    client = OllamaClient(cfg)
    opts = client._ollama_options(num_predict=100, temperature=0.2)
    assert opts["num_ctx"] == 12288
    assert opts["num_predict"] == 100
    assert opts["temperature"] == 0.2
