import pytest

from packages.contracts import ModelEndpoint
from platforms.agents.catalog import get_model
from platforms.agents.providers import ModelProviderError, OllamaModel, OpenAICompatibleModel


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, payload, headers, timeout):
        self.calls.append((url, payload, headers, timeout))
        return self.response


def test_ollama_adapter_uses_chat_api():
    transport = FakeTransport({"message": {"content": "local response"}})
    model = OllamaModel(transport)
    endpoint = ModelEndpoint("qwen", "qwen2.5:3b", "http://ollama:11434")
    assert model.generate(endpoint, "Be safe", "Hello") == "local response"
    assert transport.calls[0][0] == "http://ollama:11434/api/chat"
    assert transport.calls[0][1]["model"] == "qwen2.5:3b"


def test_vllm_adapter_uses_openai_compatible_api_and_auth():
    transport = FakeTransport({"choices": [{"message": {"content": "served response"}}]})
    model = OpenAICompatibleModel(transport, "token")
    endpoint = ModelEndpoint("mistral", "mistral-7b", "http://vllm:8000")
    assert model.generate(endpoint, "Be safe", "Hello") == "served response"
    assert transport.calls[0][0].endswith("/v1/chat/completions")
    assert transport.calls[0][2] == {"Authorization": "Bearer token"}


def test_provider_rejects_malformed_response():
    with pytest.raises(ModelProviderError):
        OllamaModel(FakeTransport({})).generate(
            ModelEndpoint("qwen", "qwen2.5:3b", "http://ollama:11434"), "system", "user"
        )


def test_catalog_records_license_and_memory_guidance():
    model = get_model("qwen-small")
    assert model.license_name == "Apache-2.0"
    assert model.minimum_memory_gb > 0
