from __future__ import annotations

import os

from fastapi import Header, HTTPException

from packages.security.auth import AuthenticationError, Identity, OIDCVerifier


def current_identity(authorization: str | None = Header(default=None)) -> Identity:
    mode = os.getenv("AUTH_MODE", "development")
    if mode == "development":
        if os.getenv("FACTORY_ENV", "development") == "production":
            raise HTTPException(status_code=503, detail="development authentication is disabled in production")
        return Identity(
            subject=os.getenv("DEV_ACTOR", "local-developer"),
            roles=frozenset(
                {
                    "factory-admin",
                    "gate-evaluator",
                    "release-approver",
                    "sre-reader",
                    "sre-proposer",
                    "sre-approver",
                    "sre-executor",
                    "judge-reviewer",
                }
            ),
            tenant=os.getenv("DEV_TENANT", "local"),
        )
    if mode != "oidc":
        raise HTTPException(status_code=503, detail="unsupported authentication mode")
    issuer = os.getenv("OIDC_ISSUER")
    audience = os.getenv("OIDC_AUDIENCE")
    if not issuer or not audience:
        raise HTTPException(status_code=503, detail="OIDC is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    try:
        return OIDCVerifier(issuer, audience).verify(authorization.removeprefix("Bearer "))
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="invalid bearer token") from exc
