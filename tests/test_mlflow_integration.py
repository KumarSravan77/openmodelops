import pytest

from platforms.integrations.http import IntegrationError, JsonResponse
from platforms.integrations.mlflow import MLflowRegistryClient


class HTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_register_promote_and_record_signed_governance():
    http = HTTP([JsonResponse(200, {"model_version": {"version": "7"}})] + [JsonResponse(200, {})] * 3)
    client = MLflowRegistryClient("http://mlflow:5000/", http=http)
    version = client.register_version("risk-model", "s3://models/sha256", "run-1", {"tenant": "bank"})
    client.promote_alias(version.name, version.version)
    client.record_governance(version.name, version.version, {"approval": "signed", "policy_digest": "sha256:abc"})
    assert version.version == "7"
    assert http.calls[0][2]["idempotent"] is False
    assert http.calls[1][2]["payload"]["alias"] == "champion"
    assert {http.calls[2][2]["payload"]["key"], http.calls[3][2]["payload"]["key"]} == {
        "openmodelops.approval",
        "openmodelops.policy_digest",
    }


def test_invalid_mlflow_response_fails_closed():
    client = MLflowRegistryClient("http://mlflow", http=HTTP([JsonResponse(200, {})]))
    with pytest.raises(IntegrationError, match="invalid"):
        client.register_version("model", "s3://artifact", "run", {})
