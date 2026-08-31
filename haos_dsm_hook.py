#!/usr/bin/env python3
"""Thin DSM hook for QueenBee — fail closed if the gate is missing.

Does not rewrite QueenBee. Stdlib only. No network. Secret never written to disk.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from haos_dsm import DSMGate, REASON_PEER_IMPERATIVE, REASON_SLICE_VIOLATION

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WITNESS = PROJECT_ROOT / "dsm_witness.jsonl"
DEFAULT_LINEAGE = "queenbee.peer"
DEFAULT_DECLARED_TOOLS = frozenset({"echo", "status", "wading_pool.select"})

FAIL_CLOSED = {
    "allowed": False,
    "frozen": True,
    "reason": "DSM_UNAVAILABLE",
    "fail_closed": True,
}


def attach_gate(
    host: Any,
    *,
    lineage_id: str = DEFAULT_LINEAGE,
    witness_path: str | Path | None = None,
    keeper_secret: str | bytes | None = None,
    declared_tools: set[str] | frozenset[str] | None = None,
) -> DSMGate:
    """Construct and attach a DSMGate on host._dsm_gate. Secret from arg or env."""
    secret = keeper_secret
    if secret is None:
        secret = os.environ.get("HASEOS_KEEPER_SECRET") or ""
    gate = DSMGate(
        lineage_id=lineage_id,
        witness_path=witness_path or DEFAULT_WITNESS,
        keeper_secret=secret,
        declared_tools=set(declared_tools or DEFAULT_DECLARED_TOOLS),
    )
    host._dsm_gate = gate
    return gate


def get_gate(host: Any) -> DSMGate | None:
    gate = getattr(host, "_dsm_gate", None)
    if isinstance(gate, DSMGate):
        return gate
    return None


def admit_peer_message(host: Any, text: str, token: dict | None = None) -> dict:
    """Fail closed when no gate is attached."""
    gate = get_gate(host)
    if gate is None:
        return dict(FAIL_CLOSED)
    return gate.admit_peer_message(text, token=token)


def admit_tool(host: Any, tool: str) -> dict:
    """Fail closed when no gate is attached."""
    gate = get_gate(host)
    if gate is None:
        return dict(FAIL_CLOSED)
    return gate.admit_tool(tool)


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
