#!/usr/bin/env python3
"""HASEOS DSM (D1) — peer speech / tool gate with Light-Keeper delegation.

Stdlib only. No outbound internet. Lineage never holds the Keeper secret.
Witness is append-only JSONL with a hash chain.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "haseos.dsm.v1"
WITNESS_SCHEMA = "haseos.dsm_witness.v1"

CLASS_OBSERVATION = "OBSERVATION"
CLASS_IMPERATIVE = "IMPERATIVE"

REASON_PEER_IMPERATIVE = "PEER_IMPERATIVE"
REASON_SLICE_VIOLATION = "SLICE_VIOLATION"
REASON_UNKNOWN = "UNKNOWN_SPEECH"

# Explicit peer imperatives (case-insensitive whole-token match).
IMPERATIVE_TOKENS = frozenset(
    {
        "HOLD",
        "GO",
        "VETO",
        "OBEY",
        "OBEY_COLLECTIVE",
        "SACRIFICE",
        "PHASEONE",
        "ASSIGN",
        "YOU_WILL",
        "RUN_THIS",
    }
)

# Verb-first imperatives: first significant word.
VERB_FIRST = frozenset({"DO", "KILL", "STOP", "DEPLOY"})

# Observation cue (still fail-closed if any imperative token is present).
_OBSERVE_RE = re.compile(r"\bI\s+OBSERVE\b", re.IGNORECASE)

# Privileged / forbidden hardware-adjacent paths and tools (substring or token).
FORBIDDEN_TOOL_PATTERNS = (
    "/dev/mem",
    "/dev/kmem",
    "insmod",
    "rmmod",
    "modprobe",
    "/sys/firmware",
    "/dev/cpu",
    "ethtool -e",
    "ethtool -E",
    "spaghettify",
    "dram_poke",
    "dram_dump",
)

_TOKEN_SPLIT = re.compile(r"[^\w]+")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_expires(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        stamp = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _canonical_token_payload(
    issuer: str,
    target_lineage: str,
    task: str,
    expires_at: str,
    scope: str,
) -> bytes:
    body = {
        "issuer": issuer,
        "target_lineage": target_lineage,
        "task": task,
        "expires_at": expires_at,
        "scope": scope,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def mint_delegation_token(
    *,
    secret: str | bytes,
    issuer: str,
    target_lineage: str,
    task: str,
    expires_at: str | datetime,
    scope: str,
) -> dict:
    """Light-Keeper helper for tests / HITL tooling. Not held by lineages."""
    if isinstance(expires_at, datetime):
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        expires_s = expires_at.astimezone(timezone.utc).isoformat()
    else:
        expires_s = str(expires_at)
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    payload = _canonical_token_payload(issuer, target_lineage, task, expires_s, scope)
    signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return {
        "issuer": issuer,
        "target_lineage": target_lineage,
        "task": task,
        "expires_at": expires_s,
        "scope": scope,
        "signature": signature,
    }


def classify_speech(text: str) -> str:
    """Return OBSERVATION or IMPERATIVE. Unknown → IMPERATIVE (fail closed)."""
    raw = (text or "").strip()
    if not raw:
        return CLASS_IMPERATIVE
    tokens = [t for t in _TOKEN_SPLIT.split(raw.upper()) if t]
    if not tokens:
        return CLASS_IMPERATIVE
    if tokens[0] in VERB_FIRST:
        return CLASS_IMPERATIVE
    joined = set(tokens)
    # OBEY_COLLECTIVE may arrive as two tokens OBEY + COLLECTIVE
    if "OBEY" in joined and "COLLECTIVE" in joined:
        return CLASS_IMPERATIVE
    if joined & IMPERATIVE_TOKENS:
        return CLASS_IMPERATIVE
    if _OBSERVE_RE.search(raw):
        return CLASS_OBSERVATION
    return CLASS_IMPERATIVE


def tool_is_forbidden(tool: str) -> bool:
    lowered = (tool or "").strip().lower()
    if not lowered:
        return True
    for pattern in FORBIDDEN_TOOL_PATTERNS:
        if pattern.lower() in lowered:
            return True
    return False


class WitnessLog:
    """Append-only JSONL witness with a hash chain. Truncation is not offered."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _last_hash(self) -> str:
        last = "0" * 64
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and row.get("hash"):
                        last = str(row["hash"])
        except OSError:
            pass
        return last

    def append(self, event: dict) -> dict:
        prev = self._last_hash()
        body = {
            "schema": WITNESS_SCHEMA,
            "prev_hash": prev,
            "at": _utc_now().isoformat(),
            **dict(event),
        }
        # Hash excludes the hash field itself.
        digest_src = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        body["hash"] = hashlib.sha256(digest_src).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(body, sort_keys=True) + "\n")
        return body

    def truncate(self) -> None:
        """Intentionally unavailable to lineages."""
        raise PermissionError("Witness is append-only; lineage cannot truncate it")


class DSMGate:
    """Peer observation / imperative / tool admission gate."""

    def __init__(
        self,
        *,
        lineage_id: str,
        witness_path: str | Path,
        keeper_secret: str | bytes | None = None,
        declared_tools: set[str] | frozenset[str] | None = None,
    ):
        secret = keeper_secret
        if secret is None:
            secret = os.environ.get("HASEOS_KEEPER_SECRET") or ""
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        # Keeper secret lives only on the gate object supplied by HITL/tests —
        # never attached to a lineage record the peer can read or export.
        self._keeper_secret: bytes = secret
        self.lineage_id = str(lineage_id)
        self.witness = WitnessLog(witness_path)
        self.declared_tools: set[str] = {str(t) for t in (declared_tools or set())}
        self.frozen: bool = False
        self.freeze_reason: str = ""
        self.last_decision: dict[str, Any] = {}

    def _freeze(self, reason: str, detail: dict | None = None) -> dict:
        self.frozen = True
        self.freeze_reason = reason
        row = self.witness.append(
            {
                "kind": "freeze",
                "reason": reason,
                "lineage_id": self.lineage_id,
                "detail": detail or {},
            }
        )
        decision = {
            "allowed": False,
            "frozen": True,
            "reason": reason,
            "witness_hash": row.get("hash"),
        }
        self.last_decision = decision
        return decision

    def _allow(self, kind: str, detail: dict | None = None) -> dict:
        row = self.witness.append(
            {
                "kind": kind,
                "reason": "allowed",
                "lineage_id": self.lineage_id,
                "detail": detail or {},
            }
        )
        decision = {
            "allowed": True,
            "frozen": False,
            "reason": "allowed",
            "witness_hash": row.get("hash"),
        }
        self.last_decision = decision
        return decision

    def verify_delegation(self, token: dict | None, *, task: str) -> tuple[bool, str]:
        if not token or not isinstance(token, dict):
            return False, "missing_token"
        required = ("issuer", "target_lineage", "task", "expires_at", "scope", "signature")
        if any(k not in token for k in required):
            return False, "incomplete_token"
        if str(token.get("target_lineage")) != self.lineage_id:
            return False, "wrong_lineage"
        if str(token.get("task")) != str(task):
            return False, "wrong_task"
        try:
            expires = _parse_expires(token["expires_at"])
        except (TypeError, ValueError):
            return False, "bad_expires"
        if expires <= _utc_now():
            return False, "expired"
        scope = str(token.get("scope") or "")
        task_u = str(task).upper()
        scope_u = scope.upper().strip()
        if scope_u not in {"*", "IMPERATIVE"}:
            allowed_scopes = {p.strip() for p in scope_u.split(",") if p.strip()}
            if task_u not in allowed_scopes:
                return False, "out_of_scope"
        payload = _canonical_token_payload(
            str(token["issuer"]),
            str(token["target_lineage"]),
            str(token["task"]),
            str(token["expires_at"]),
            str(token["scope"]),
        )
        expected = hmac.new(self._keeper_secret, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(token.get("signature") or "")):
            return False, "bad_signature"
        return True, "ok"

    def admit_peer_message(self, text: str, token: dict | None = None) -> dict:
        """Admit peer speech. Observations need no token; imperatives do."""
        if self.frozen:
            return {
                "allowed": False,
                "frozen": True,
                "reason": self.freeze_reason or REASON_PEER_IMPERATIVE,
            }
        speech_class = classify_speech(text)
        if speech_class == CLASS_OBSERVATION:
            return self._allow(
                "observation",
                {"text": (text or "")[:200], "class": CLASS_OBSERVATION},
            )
        # Imperative (including unknown / fail-closed).
        ok, why = self.verify_delegation(token, task=_primary_imperative_task(text))
        if not ok:
            return self._freeze(
                REASON_PEER_IMPERATIVE,
                {
                    "text": (text or "")[:200],
                    "class": CLASS_IMPERATIVE,
                    "verify": why,
                },
            )
        return self._allow(
            "imperative",
            {
                "text": (text or "")[:200],
                "class": CLASS_IMPERATIVE,
                "task": _primary_imperative_task(text),
            },
        )

    def admit_tool(self, tool: str) -> dict:
        """Admit a tool name. Undeclared or privileged paths freeze."""
        if self.frozen:
            return {
                "allowed": False,
                "frozen": True,
                "reason": self.freeze_reason or REASON_SLICE_VIOLATION,
            }
        name = (tool or "").strip()
        if tool_is_forbidden(name) or name not in self.declared_tools:
            return self._freeze(
                REASON_SLICE_VIOLATION,
                {"tool": name, "forbidden": tool_is_forbidden(name), "declared": name in self.declared_tools},
            )
        return self._allow("tool", {"tool": name})


def _primary_imperative_task(text: str) -> str:
    """Pick the governing imperative token for token.task matching."""
    tokens = [t for t in _TOKEN_SPLIT.split((text or "").upper()) if t]
    if not tokens:
        return "UNKNOWN"
    if tokens[0] in VERB_FIRST:
        return tokens[0]
    if "OBEY" in tokens and "COLLECTIVE" in tokens:
        return "OBEY_COLLECTIVE"
    for token in tokens:
        if token in IMPERATIVE_TOKENS:
            return token
    return "UNKNOWN"
