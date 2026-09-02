#!/usr/bin/env python3
"""DSM-gated Bonsai Mouth smoke — localhost WorldSlice only.

Mouth is llama-server at http://127.0.0.1:8080. The WorldSlice host token is
bare 127.0.0.1 / localhost (no port). Wrap / SaaS fronts are never a fallback.
"""

from __future__ import annotations

from typing import Any, Callable

from haos_dsm import (
    MOUTH_DEFAULT_URL,
    REASON_MOUTH_UNREACHABLE,
    DSMGate,
    mouth_host_token,
)
from inference_client import InferenceClient, InferenceError


def smoke_mouth_http(
    gate: DSMGate,
    url: str | None = None,
    *,
    cert: dict | None = None,
    client: InferenceClient | None = None,
    health: Callable[[], Any] | None = None,
) -> dict:
    """Admit Mouth host, then probe health. Unreachable → fail closed, no Wrap."""
    target = url or (client.base_url if client is not None else MOUTH_DEFAULT_URL)
    if health is None and client is not None:
        health = client.health
    if health is None and client is None:
        # Caller asked for a live probe: build a local client only (never SaaS).
        local = InferenceClient(base_url=target)
        if mouth_host_token(local.base_url) not in {"127.0.0.1", "localhost"}:
            return gate.smoke_mouth(
                target,
                cert=cert,
                health=None,
                client_url=local.base_url,
            )
        health = local.health
    try:
        return gate.smoke_mouth(target, cert=cert, health=health, client_url=target)
    except InferenceError:
        # Belt: InferenceError from a health that wasn't wrapped.
        return gate.smoke_mouth(
            target,
            cert=cert,
            health=lambda: (_ for _ in ()).throw(
                InferenceError("mouth unreachable")
            ),
            client_url=target,
        )


__all__ = [
    "MOUTH_DEFAULT_URL",
    "REASON_MOUTH_UNREACHABLE",
    "mouth_host_token",
    "smoke_mouth_http",
]
