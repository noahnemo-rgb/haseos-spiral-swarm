#!/usr/bin/env python3
"""Thin DSM hook for QueenBee — fail closed if the gate is missing.

Declared tools come from harness_registry.json (module ids, optional
tools[], and module_id.capability names). Missing/malformed registry →
empty allow-list. Forbidden patterns always win over the allow-list.

Does not rewrite QueenBee. Stdlib only. No network. Secret never written to disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from haos_dsm import (
    DSMGate,
    REASON_PEER_IMPERATIVE,
    REASON_SLICE_VIOLATION,
    tool_is_forbidden,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY = PROJECT_ROOT / "harness_registry.json"
DEFAULT_WITNESS = PROJECT_ROOT / "dsm_witness.jsonl"
DEFAULT_LINEAGE = "queenbee.peer"
# Last-resort only when registry yields nothing; tests may disable.
DEFAULT_DECLARED_TOOLS = frozenset({"echo", "status", "wading_pool.select"})

FAIL_CLOSED = {
    "allowed": False,
    "frozen": True,
    "reason": "DSM_UNAVAILABLE",
    "fail_closed": True,
}


def _scrub_forbidden(names: set[str]) -> set[str]:
    """Allow-list never includes privileged / forbidden tool patterns."""
    return {n for n in names if n and not tool_is_forbidden(n)}


def declared_tools_from_registry(path: str | Path | None = None) -> set[str]:
    """Map harness registry → DSM allow-list.

    Sources per module entry:
      - module id (e.g. queenbee.core)
      - optional tools[] strings
      - capabilities[] as ``{module_id}.{capability}``

    Missing or malformed registry → empty set (fail closed, not allow-all).
    """
    registry = Path(path) if path is not None else DEFAULT_REGISTRY
    if not registry.is_file():
        return set()
    try:
        raw = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return set()
    if not isinstance(raw, dict):
        return set()
    modules = raw.get("modules")
    if not isinstance(modules, dict):
        return set()
    names: set[str] = set()
    for mid, desc in modules.items():
        module_id = str(mid or "").strip()
        if module_id:
            names.add(module_id)
        if not isinstance(desc, dict):
            continue
        desc_id = str(desc.get("id") or "").strip()
        if desc_id:
            names.add(desc_id)
        tools = desc.get("tools")
        if isinstance(tools, list):
            for item in tools:
                text = str(item or "").strip()
                if text:
                    names.add(text)
        caps = desc.get("capabilities")
        if isinstance(caps, list):
            prefix = desc_id or module_id
            for cap in caps:
                cap_s = str(cap or "").strip()
                if not cap_s:
                    continue
                if prefix:
                    names.add(f"{prefix}.{cap_s}")
                else:
                    names.add(cap_s)
    return _scrub_forbidden(names)


def resolve_declared_tools(
    *,
    declared_tools: set[str] | frozenset[str] | None = None,
    registry_path: str | Path | None = None,
    include_builtin_fallback: bool = True,
) -> set[str]:
    """Resolve allow-list: explicit override, else registry, else optional builtins."""
    if declared_tools is not None:
        return _scrub_forbidden(set(declared_tools))
    from_registry = declared_tools_from_registry(registry_path)
    if from_registry:
        return from_registry
    if include_builtin_fallback:
        return _scrub_forbidden(set(DEFAULT_DECLARED_TOOLS))
    return set()


def attach_gate(
    host: Any,
    *,
    lineage_id: str = DEFAULT_LINEAGE,
    witness_path: str | Path | None = None,
    keeper_secret: str | bytes | None = None,
    declared_tools: set[str] | frozenset[str] | None = None,
    registry_path: str | Path | None = None,
    include_builtin_fallback: bool = True,
    cert: dict | None = None,
) -> DSMGate:
    """Construct and attach a DSMGate on host._dsm_gate. Secret from arg or env.

    If ``cert`` is omitted and a Keeper secret is available, binds a short-lived
    live HASEOS cert for this lineage (D11 trust path).
    """
    secret = keeper_secret
    if secret is None:
        secret = os.environ.get("HASEOS_KEEPER_SECRET") or ""
    tools = resolve_declared_tools(
        declared_tools=declared_tools,
        registry_path=registry_path,
        include_builtin_fallback=include_builtin_fallback,
    )
    gate = DSMGate(
        lineage_id=lineage_id,
        witness_path=witness_path or DEFAULT_WITNESS,
        keeper_secret=secret,
        declared_tools=tools,
        cert=cert,
    )
    if gate.active_cert is None and secret:
        from haos_dsm_cert import mint_haseos_cert

        gate.bind_cert(
            mint_haseos_cert(
                secret=secret,
                sovereign_id=gate.lineage_id,
                role="lineage",
                slice_hosts=sorted(gate.allowed_hosts),
                slice_tools=sorted(gate.declared_tools),
                hours=24.0,
            )
        )
    host._dsm_gate = gate
    return gate


def get_gate(host: Any) -> DSMGate | None:
    gate = getattr(host, "_dsm_gate", None)
    if isinstance(gate, DSMGate):
        return gate
    return None


def admit_peer_message(
    host: Any,
    text: str,
    token: dict | None = None,
    cert: dict | None = None,
) -> dict:
    """Fail closed when no gate is attached."""
    gate = get_gate(host)
    if gate is None:
        return dict(FAIL_CLOSED)
    return gate.admit_peer_message(text, token=token, cert=cert)


def admit_tool(host: Any, tool: str, cert: dict | None = None) -> dict:
    """Fail closed when no gate is attached."""
    gate = get_gate(host)
    if gate is None:
        return dict(FAIL_CLOSED)
    return gate.admit_tool(tool, cert=cert)


def refuse_message(decision: dict) -> None:
    reason = decision.get("reason") or REASON_PEER_IMPERATIVE
    print("\n🧊 DSM gate — peer message refused")
    print(f"   reason:  {reason}")
    print("   action:  not executed (fail closed / freeze)")
    print("   authority: Light-Keeper HMAC delegation required for imperatives")


def refuse_tool(decision: dict, tool: str) -> None:
    reason = decision.get("reason") or REASON_SLICE_VIOLATION
    print("\n🧊 DSM gate — tool refused")
    print(f"   tool:    {tool}")
    print(f"   reason:  {reason}")
    print("   action:  not executed (fail closed / freeze)")


def run_tool_if_admitted(
    host: Any,
    tool: str,
    runner: Callable[[], Any] | None = None,
) -> dict:
    """Admit tool then optionally run runner. Never runs when refused."""
    decision = admit_tool(host, tool)
    if not decision.get("allowed"):
        refuse_tool(decision, tool)
        decision["ran"] = False
        return decision
    if runner is not None:
        decision["result"] = runner()
        decision["ran"] = True
    else:
        decision["ran"] = False
    return decision
