from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

import jwt


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Identity:
    subject: str
    roles: frozenset[str]
    tenant: str


class OIDCVerifier:
    def __init__(self, issuer: str, audience: str, cache_seconds: int = 3600) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.cache_seconds = cache_seconds
        self._jwks: dict | None = None
        self._expires_at = 0.0

    def _keys(self) -> dict:
        if self._jwks is None or time.time() >= self._expires_at:
            with urllib.request.urlopen(f"{self.issuer}/protocol/openid-connect/certs", timeout=5) as response:
                self._jwks = json.loads(response.read())
            self._expires_at = time.time() + self.cache_seconds
        return self._jwks

    def verify(self, token: str) -> Identity:
        try:
            header = jwt.get_unverified_header(token)
            key = next(item for item in self._keys()["keys"] if item["kid"] == header["kid"])
            payload = jwt.decode(
                token, jwt.PyJWK(key).key, algorithms=[header["alg"]], audience=self.audience, issuer=self.issuer
            )
        except Exception as exc:
            raise AuthenticationError("token verification failed") from exc
        realm_roles = payload.get("realm_access", {}).get("roles", [])
        client_roles = payload.get("resource_access", {}).get(self.audience, {}).get("roles", [])
        tenant = payload.get("tenant_id", "default")
        return Identity(str(payload["sub"]), frozenset(realm_roles + client_roles), str(tenant))


def require_roles(*required: str) -> Callable[[Identity], Identity]:
    required_set = frozenset(required)

    def authorize(identity: Identity) -> Identity:
        if not required_set.issubset(identity.roles):
            raise AuthorizationError(f"required roles missing: {sorted(required_set - identity.roles)}")
        return identity

    return authorize
