import pytest

from packages.contracts import ModelEndpoint, ModelRelease


def test_model_endpoint_contract():
    endpoint = ModelEndpoint("fraud", "v12", "https://models.example.test")
    assert endpoint.protocol == "openai-compatible"
    with pytest.raises(ValueError):
        ModelEndpoint("fraud", "v12", "file:///tmp/model")


def test_release_requires_immutable_digest():
    ModelRelease("fraud", "12", "sha256:" + "f" * 64, "production")
    with pytest.raises(ValueError):
        ModelRelease("fraud", "12", "latest", "production")
