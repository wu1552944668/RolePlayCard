from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import providers


def test_text_provider_prepends_prefix_prompt(monkeypatch):
    captured: dict[str, object] = {}

    def fake_openai_request_json(config, method, path, payload=None):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(providers, "_openai_request_json", fake_openai_request_json)
    provider = providers.OpenAICompatibleTextProvider()
    provider.generate(
        {
            "baseUrl": "https://example.com/v1",
            "apiKey": "test-key",
            "model": "test-model",
            "prefixPrompt": "这是前置破限提示词",
        },
        "这是正常提示词",
    )

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["messages"][0]["content"] == "这是前置破限提示词\n\n这是正常提示词"


def test_text_provider_uses_original_prompt_without_prefix(monkeypatch):
    captured: dict[str, object] = {}

    def fake_openai_request_json(config, method, path, payload=None):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(providers, "_openai_request_json", fake_openai_request_json)
    provider = providers.OpenAICompatibleTextProvider()
    provider.generate(
        {
            "baseUrl": "https://example.com/v1",
            "apiKey": "test-key",
            "model": "test-model",
            "prefixPrompt": "",
        },
        "这是正常提示词",
    )

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["messages"][0]["content"] == "这是正常提示词"
