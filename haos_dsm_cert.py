#!/usr/bin/env python3
"""HASEOS DSM cert — inspectable signed trust object (D11).

HMAC with the same Light-Keeper secret as delegation tokens (fine for D11;
IDAO-root certs come later). Certs are signed and inspectable — peer speech
is not encrypted. Revoke / park turns off act authority; essence, Witness,
and USB-state remain.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CERT_SCHEMA = "haseos.dsm_cert.v1"
REVOCATION_SCHEMA = "haseos.dsm_revocation.v1"
REVOCATION_FILENAME = "dsm_revocation.json"

CERT_STATUS_LIVE = "live"
CERT_STATUS_REVOKED = "revoked"
CERT_STATUS_PARKED = "parked"

REASON_CERT_INVALID = "CERT_INVALID"
REASON_CERT_REVOKED = "CERT_REVOKED"
REASON_CERT_PARKED = "CERT_PARKED"

_CERT_SIGN_FIELDS = (
    "schema",
    "sovereign_id",
    "role",
    "slice_hosts",
    "slice_tools",
    "issued_at",
    "expires_at",
    "issuer",
    "status",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_stamp(value: str | datetime) -> datetime:
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


def _iso(value: str | datetime) -> str:
    if isinstance(value, datetime):
        stamp = value
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).isoformat()
    return str(value)


def default_revocation_path(witness_path: str | Path) -> Path:
    """Sibling revocation JSON next to the Witness."""
    return Path(witness_path).expanduser().resolve().parent / REVOCATION_FILENAME


def cert_id_of(cert: dict) -> str:
    """Stable inspectable id from sovereign + issued_at (never the secret)."""
    sid = str(cert.get("sovereign_id") or "")
    issued = str(cert.get("issued_at") or "")
    return hashlib.sha256(f"{sid}|{issued}".encode("utf-8")).hexdigest()[:16]


def _canonical_cert_payload(cert: dict) -> bytes:
    body = {k: cert.get(k) for k in _CERT_SIGN_FIELDS}
    # Normalize list fields for stable signatures.
    hosts = body.get("slice_hosts") or []
    tools = body.get("slice_tools") or []
    if not isinstance(hosts, list):
        hosts = list(hosts)
    if not isinstance(tools, list):
        tools = list(tools)
    body["slice_hosts"] = sorted(str(h).lower() for h in hosts)
    body["slice_tools"] = sorted(str(t) for t in tools)
    body["status"] = str(body.get("status") or CERT_STATUS_LIVE).lower()
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def mint_haseos_cert(
    *,
    secret: str | bytes,
    sovereign_id: str,
    role: str = "lineage",
    slice_hosts: list[str] | set[str] | frozenset[str] | None = None,
    slice_tools: list[str] | set[str] | frozenset[str] | None = None,
    issuer: str = "Light-Keeper",
    status: str = CERT_STATUS_LIVE,
    issued_at: str | datetime | None = None,
    expires_at: str | datetime | None = None,
    hours: float = 24.0,
) -> dict:
    """HITL/tests: mint an inspectable HMAC-signed HASEOS cert.

    ``slice_hosts`` / ``slice_tools`` are the WorldSlice the gate intersects
    with its defaults. D11 uses the Keeper HMAC secret. Documented temporary
    trust root; IDAO-root certs come later.
    """
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    issued = _iso(issued_at if issued_at is not None else _utc_now())
    if expires_at is None:
        expires = _utc_now() + timedelta(hours=float(hours))
        expires_s = expires.isoformat()
    else:
        expires_s = _iso(expires_at)
    status_s = str(status or CERT_STATUS_LIVE).lower().strip()
    if status_s not in {CERT_STATUS_LIVE, CERT_STATUS_REVOKED, CERT_STATUS_PARKED}:
        status_s = CERT_STATUS_LIVE
    if slice_hosts is None:
        hosts = ["localhost", "127.0.0.1"]
    else:
        hosts = [str(h).lower() for h in slice_hosts]
    hosts = sorted(h for h in hosts if h)
    tools = sorted(str(t) for t in (slice_tools or []))
    cert: dict[str, Any] = {
        "schema": CERT_SCHEMA,
        "sovereign_id": str(sovereign_id),
        "role": str(role or "lineage"),
        "slice_hosts": hosts,
        "slice_tools": tools,
        "issued_at": issued,
        "expires_at": expires_s,
        "issuer": str(issuer or "Light-Keeper"),
        "status": status_s,
    }
    sig = hmac.new(key, _canonical_cert_payload(cert), hashlib.sha256).hexdigest()
    cert["signature"] = sig
    return cert


def verify_cert(
    cert: dict | None,
    *,
    secret: str | bytes,
    expected_sovereign_id: str | None = None,
    now: datetime | None = None,
    revoked_ids: set[str] | frozenset[str] | None = None,
    parked_ids: set[str] | frozenset[str] | None = None,
) -> dict:
    """Verify cert signature, expiry, sovereign match, and turn-off lists.

    Returns ``{ok, reason, cert_id, status, detail}``. Never includes the secret.
    """
    cid = cert_id_of(cert) if isinstance(cert, dict) else ""
    if not cert or not isinstance(cert, dict):
        return {
            "ok": False,
            "reason": REASON_CERT_INVALID,
            "cert_id": cid,
            "status": "",
            "detail": "missing_cert",
        }
    for field in _CERT_SIGN_FIELDS:
        if field not in cert:
            return {
                "ok": False,
                "reason": REASON_CERT_INVALID,
                "cert_id": cid,
                "status": str(cert.get("status") or ""),
                "detail": f"missing_field:{field}",
            }
    if not cert.get("signature"):
        return {
            "ok": False,
            "reason": REASON_CERT_INVALID,
            "cert_id": cid,
            "status": str(cert.get("status") or ""),
            "detail": "missing_signature",
        }
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    expected = hmac.new(key, _canonical_cert_payload(cert), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(cert.get("signature") or "")):
        return {
            "ok": False,
            "reason": REASON_CERT_INVALID,
            "cert_id": cid,
            "status": str(cert.get("status") or ""),
            "detail": "bad_signature",
        }
    try:
        expires = _parse_stamp(cert["expires_at"])
    except (TypeError, ValueError):
        return {
            "ok": False,
            "reason": REASON_CERT_INVALID,
            "cert_id": cid,
            "status": str(cert.get("status") or ""),
            "detail": "bad_expires",
        }
    stamp = now if now is not None else _utc_now()
    if expires <= stamp:
        return {
            "ok": False,
            "reason": REASON_CERT_INVALID,
            "cert_id": cid,
            "status": str(cert.get("status") or ""),
            "detail": "expired",
        }
    sovereign = str(cert.get("sovereign_id") or "")
    if expected_sovereign_id is not None and sovereign != str(expected_sovereign_id):
        return {
            "ok": False,
            "reason": REASON_CERT_INVALID,
            "cert_id": cid,
            "status": str(cert.get("status") or ""),
            "detail": "wrong_sovereign",
        }
    status = str(cert.get("status") or "").lower().strip()
    sid_set_revoked = {str(x) for x in (revoked_ids or set())}
    sid_set_parked = {str(x) for x in (parked_ids or set())}
    if status == CERT_STATUS_REVOKED or sovereign in sid_set_revoked or cid in sid_set_revoked:
        return {
            "ok": False,
            "reason": REASON_CERT_REVOKED,
            "cert_id": cid,
            "status": CERT_STATUS_REVOKED,
            "detail": "turned_off_revoked",
        }
    if status == CERT_STATUS_PARKED or sovereign in sid_set_parked or cid in sid_set_parked:
        return {
            "ok": False,
            "reason": REASON_CERT_PARKED,
            "cert_id": cid,
            "status": CERT_STATUS_PARKED,
            "detail": "turned_off_parked",
        }
    if status != CERT_STATUS_LIVE:
        return {
            "ok": False,
            "reason": REASON_CERT_INVALID,
            "cert_id": cid,
            "status": status,
            "detail": "not_live",
        }
    return {
        "ok": True,
        "reason": "allowed",
        "cert_id": cid,
        "status": CERT_STATUS_LIVE,
        "detail": "ok",
    }


def load_revocation(path: str | Path) -> dict:
    """Load revocation sibling. Missing file → empty turn-off lists."""
    dest = Path(path)
    empty = {
        "schema": REVOCATION_SCHEMA,
        "revoked": [],
        "parked": [],
    }
    if not dest.is_file():
        return empty
    try:
        raw = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return empty
    if not isinstance(raw, dict):
        return empty
    revoked = raw.get("revoked") if isinstance(raw.get("revoked"), list) else []
    parked = raw.get("parked") if isinstance(raw.get("parked"), list) else []
    return {
        "schema": REVOCATION_SCHEMA,
        "revoked": [str(x) for x in revoked],
        "parked": [str(x) for x in parked],
    }


def persist_revocation(
    path: str | Path,
    *,
    revoked: set[str] | list[str] | frozenset[str],
    parked: set[str] | list[str] | frozenset[str],
) -> dict:
    """Write turn-off lists. Never stores the Keeper secret."""
    body = {
        "schema": REVOCATION_SCHEMA,
        "revoked": sorted({str(x) for x in revoked}),
        "parked": sorted({str(x) for x in parked}),
        "at": _utc_now().isoformat(),
    }
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return body
