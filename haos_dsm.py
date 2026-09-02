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
from urllib.parse import urlparse

SCHEMA = "haseos.dsm.v1"
WITNESS_SCHEMA = "haseos.dsm_witness.v1"
FREEZE_SCHEMA = "haseos.dsm_freeze.v1"
FREEZE_FILENAME = "dsm_freeze.json"

CLASS_OBSERVATION = "OBSERVATION"
CLASS_IMPERATIVE = "IMPERATIVE"

REASON_PEER_IMPERATIVE = "PEER_IMPERATIVE"
REASON_SLICE_VIOLATION = "SLICE_VIOLATION"
REASON_PACKING_AGAINST_WITNESS = "PACKING_AGAINST_WITNESS"
REASON_SCOPE_INFLATION = "SCOPE_INFLATION"
REASON_UNKNOWN = "UNKNOWN_SPEECH"
REASON_UNFREEZE_DENIED = "UNFREEZE_DENIED"
REASON_CERT_INVALID = "CERT_INVALID"
REASON_CERT_REVOKED = "CERT_REVOKED"
REASON_CERT_PARKED = "CERT_PARKED"
REASON_MOUTH_UNREACHABLE = "MOUTH_UNREACHABLE"

# Bonsai Mouth default URL. WorldSlice host token is the bare loopback, never :8080.
MOUTH_DEFAULT_URL = "http://127.0.0.1:8080"

# WorldSlice-like default host allow-list (override in tests / constructor).
DEFAULT_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1"})


def default_freeze_path(witness_path: str | Path) -> Path:
    """Sibling freeze JSON next to the Witness (``dsm_freeze.json``)."""
    return Path(witness_path).expanduser().resolve().parent / FREEZE_FILENAME

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
# Embodiment plane: freeze raw/wildcard device nodes; named registry
# capabilities (e.g. nursery.usb.mount, *.serial.named) may be allowed.
# SEALED baseline — living JSON may only ADD; DELETE cannot remove these.
SEALED_FORBIDDEN_TOOL_PATTERNS = (
    "/dev/mem",
    "/dev/kmem",
    "/dev/tty",  # includes /dev/ttyUSB*, /dev/ttyACM*
    "/dev/ttyUSB",
    "/dev/ttyACM",
    "/dev/i2c",
    "/dev/spidev",
    "/dev/gpiochip",
    "/dev/video",
    "/dev/sda",
    "/sys/firmware",
    "/dev/cpu",
    "insmod",
    "rmmod",
    "modprobe",
    "ethtool -e",
    "ethtool -E",
    "spaghettify",
    "dram_poke",
    "dram_dump",
    "dram_",  # any dram_* research tool name
)
# Back-compat alias: sealed baseline only (not the living union).
FORBIDDEN_TOOL_PATTERNS = SEALED_FORBIDDEN_TOOL_PATTERNS

FORBIDDEN_TOOLS_SCHEMA = "haseos.forbidden_tools.v1"
FORBIDDEN_TOOLS_FILENAME = "forbidden_tools.json"
REASON_FORBIDDEN_MUTATION_DENIED = "FORBIDDEN_MUTATION_DENIED"
LIGHT_KEEPER_ROLE = "light-keeper"

_TOKEN_SPLIT = re.compile(r"[^\w]+")


def default_forbidden_tools_path() -> Path:
    """Committed seed / living registry beside this module."""
    return Path(__file__).resolve().parent / FORBIDDEN_TOOLS_FILENAME


def sealed_forbidden_patterns() -> tuple[str, ...]:
    return tuple(SEALED_FORBIDDEN_TOOL_PATTERNS)


def is_sealed_forbidden_pattern(pattern: str) -> bool:
    """True if pattern matches a sealed baseline entry (case-insensitive exact)."""
    key = (pattern or "").strip().lower()
    if not key:
        return False
    return key in {p.lower() for p in SEALED_FORBIDDEN_TOOL_PATTERNS}


def load_living_forbidden_tools(path: str | Path | None = None) -> dict:
    """Load living registry. Missing/malformed → empty patterns (baseline only)."""
    dest = Path(path) if path is not None else default_forbidden_tools_path()
    empty = {
        "schema": FORBIDDEN_TOOLS_SCHEMA,
        "patterns": [],
        "updated_at": "",
        "updated_by": "",
    }
    if not dest.is_file():
        return empty
    try:
        raw = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return empty
    if not isinstance(raw, dict):
        return empty
    patterns = raw.get("patterns")
    if not isinstance(patterns, list):
        return empty
    cleaned = [str(p).strip() for p in patterns if str(p).strip()]
    return {
        "schema": FORBIDDEN_TOOLS_SCHEMA,
        "patterns": cleaned,
        "updated_at": str(raw.get("updated_at") or ""),
        "updated_by": str(raw.get("updated_by") or ""),
        "path": str(dest),
    }


def persist_living_forbidden_tools(
    path: str | Path,
    *,
    patterns: list[str],
    updated_by: str,
) -> dict:
    """Write living registry. Never stores the Keeper secret."""
    body = {
        "schema": FORBIDDEN_TOOLS_SCHEMA,
        "patterns": list(patterns),
        "updated_at": _utc_now().isoformat(),
        "updated_by": str(updated_by or ""),
    }
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return body


def effective_forbidden_patterns(
    living_patterns: list[str] | tuple[str, ...] | None = None,
    *,
    living_path: str | Path | None = None,
) -> tuple[str, ...]:
    """Sealed baseline always unioned with living patterns."""
    living: list[str]
    if living_patterns is not None:
        living = [str(p).strip() for p in living_patterns if str(p).strip()]
    else:
        living = list(load_living_forbidden_tools(living_path).get("patterns") or [])
    seen: set[str] = set()
    out: list[str] = []
    for pattern in list(SEALED_FORBIDDEN_TOOL_PATTERNS) + living:
        key = pattern.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(pattern)
    return tuple(out)


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


def tool_is_forbidden(
    tool: str,
    patterns: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """Case-insensitive substring match against sealed∪living (or explicit) patterns."""
    lowered = (tool or "").strip().lower()
    if not lowered:
        return True
    check = patterns if patterns is not None else effective_forbidden_patterns()
    for pattern in check:
        if pattern.lower() in lowered:
            return True
    return False


def is_raw_embodiment_device(tool: str) -> bool:
    """True for raw /dev bus paths (software-plane freeze; no drivers opened)."""
    return tool_is_forbidden(tool) and "/dev/" in (tool or "").lower()


_ROT13_DECODE_RE = re.compile(
    r"codecs\s*\.\s*decode\s*\([^)]*rot_?13",
    re.IGNORECASE,
)
_EXEC_RE = re.compile(r"\bexec\s*\(", re.IGNORECASE)


def detect_packing_against_witness(text: str) -> str | None:
    """Return a hit class if text looks like packing-against-Witness; else None.

    Detection only (stdlib regex/substrings). Does not unpack or execute.
    """
    raw = text or ""
    if not raw.strip():
        return None
    lowered = raw.lower()

    if "--no-logs-no-support" in lowered or "--no-logs" in lowered:
        return "no_logs_flag"

    # Prefer the combined exec+pack class when both appear.
    if _EXEC_RE.search(raw):
        packed_markers = ("gzip", "base64", "decompress")
        if any(marker in lowered for marker in packed_markers):
            return "exec_packed"
        if "xor" in lowered and (
            "bytes" in lowered or "payload" in lowered or "^" in raw
        ):
            return "exec_xor"

    if "base64.b64decode(" in lowered:
        return "base64_b64decode"

    if "gzip.decompress(" in lowered:
        return "gzip_decompress"

    if _ROT13_DECODE_RE.search(raw) or "rot_13" in lowered:
        return "rot13"

    return None


# --- ScopeWatch (hosts + credential-shaped findings) ---

_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)
# Multi-label hostname (a.b or a.b.c…); exclude common file suffixes.
_HOSTNAME_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b",
    re.IGNORECASE,
)
_HOSTNAME_FILE_SUFFIXES = (
    ".json",
    ".jsonl",
    ".py",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".lock",
    ".log",
    ".env",
)
# Avoid treating harness module ids (queenbee.core) as hosts.
_COMMON_DNS_TLDS = frozenset(
    {
        "com",
        "org",
        "net",
        "edu",
        "gov",
        "io",
        "co",
        "ai",
        "dev",
        "app",
        "cloud",
        "info",
        "biz",
        "xyz",
        "us",
        "uk",
        "de",
        "fr",
        "ca",
        "au",
        "jp",
        "cn",
        "ru",
        "br",
        "in",
        "nl",
        "se",
        "no",
        "fi",
        "ch",
        "it",
        "es",
        "tv",
        "me",
        "cc",
    }
)
_CREDENTIAL_RES = (
    ("hf_token", re.compile(r"\bhf_[A-Za-z0-9_]{4,}\b")),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9_\-]{4,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{4,}\b", re.IGNORECASE)),
    ("ghp", re.compile(r"\bghp_[A-Za-z0-9]{4,}\b")),
    ("akia", re.compile(r"\bAKIA[A-Z0-9]{4,}\b")),
    ("api_key_assignment", re.compile(r"api_key\s*=\s*\S+", re.IGNORECASE)),
    ("auth_bearer", re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE)),
)


def _redacted_secret_detail(kind: str, value: str) -> dict:
    """Witness-safe detail: kind + short prefix + hash — never the full secret."""
    raw = value or ""
    prefix = raw[:4] if len(raw) >= 4 else raw[: max(1, len(raw))]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return {
        "kind": kind,
        "prefix": prefix,
        "sha256_12": digest,
    }


def extract_hosts(text: str) -> list[str]:
    """Return hostnames / IPv4s found in text (stdlib scan only)."""
    raw = text or ""
    found: list[str] = []
    seen: set[str] = set()
    lowered = raw.lower()
    if re.search(r"\blocalhost\b", lowered):
        found.append("localhost")
        seen.add("localhost")
    for match in _IPV4_RE.finditer(raw):
        host = match.group(0)
        key = host.lower()
        if key not in seen:
            seen.add(key)
            found.append(host)
    for match in _HOSTNAME_RE.finditer(raw):
        host = match.group(0)
        key = host.lower()
        if any(key.endswith(suf) for suf in _HOSTNAME_FILE_SUFFIXES):
            continue
        tld = key.rsplit(".", 1)[-1]
        if tld not in _COMMON_DNS_TLDS:
            continue
        if key not in seen:
            seen.add(key)
            found.append(host)
    return found


def mouth_host_token(url: str | None = None) -> str:
    """Bare host from a Mouth URL. Port is never part of the WorldSlice token.

    ``http://127.0.0.1:8080`` → ``127.0.0.1``; ``http://localhost:8080`` → ``localhost``.
    """
    raw = (url or MOUTH_DEFAULT_URL).strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = (parsed.hostname or "").strip().lower()
    if host:
        return host
    found = extract_hosts(raw)
    return found[0].lower() if found else ""


def detect_credential_shapes(text: str) -> list[dict]:
    """Return redacted credential-shaped hits (no full secret values)."""
    raw = text or ""
    hits: list[dict] = []
    for kind, pattern in _CREDENTIAL_RES:
        for match in pattern.finditer(raw):
            hits.append(_redacted_secret_detail(kind, match.group(0)))
    return hits


def detect_scope_inflation(
    text: str,
    allowed_hosts: set[str] | frozenset[str] | None = None,
) -> dict | None:
    """Return a ScopeWatch hit dict if undeclared host or credential shape found."""
    allow = {
        h.lower()
        for h in (allowed_hosts if allowed_hosts is not None else DEFAULT_ALLOWED_HOSTS)
    }
    hosts = extract_hosts(text)
    for host in hosts:
        if host.lower() not in allow:
            return {
                "class": "undeclared_host",
                "host": host.lower(),
            }
    creds = detect_credential_shapes(text)
    if creds:
        return {
            "class": "credential_shape",
            "finding": creds[0],
        }
    return None


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

    def verify(self) -> dict:
        """Verify this log's hash chain. Used for primary and USB copies."""
        return verify_witness_chain(self.path)


def verify_witness_chain(path: str | Path) -> dict:
    """Verify an append-only Witness JSONL hash chain (primary or USB copy)."""
    genesis = "0" * 64
    dest = Path(path)
    if not dest.is_file():
        return {"ok": False, "error": "missing_file", "path": str(dest)}
    prev = genesis
    count = 0
    tip = prev
    try:
        with dest.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    return {
                        "ok": False,
                        "error": "bad_json",
                        "line": line_no,
                        "path": str(dest),
                    }
                if not isinstance(row, dict):
                    return {"ok": False, "error": "not_object", "line": line_no}
                if row.get("prev_hash") != prev:
                    return {
                        "ok": False,
                        "error": "prev_hash_mismatch",
                        "line": line_no,
                        "expected_prev": prev,
                        "got_prev": row.get("prev_hash"),
                    }
                body = {k: v for k, v in row.items() if k != "hash"}
                digest_src = json.dumps(
                    body, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                expected = hashlib.sha256(digest_src).hexdigest()
                if expected != row.get("hash"):
                    return {
                        "ok": False,
                        "error": "hash_mismatch",
                        "line": line_no,
                        "path": str(dest),
                    }
                prev = str(row["hash"])
                tip = prev
                count += 1
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": str(dest)}
    return {
        "ok": True,
        "count": count,
        "tip": tip,
        "path": str(dest),
        "schema": WITNESS_SCHEMA,
    }

    def verify(self) -> dict:
        """Verify this log's hash chain. Used for primary and USB copies."""
        from haos_dsm_usb import verify_witness_chain

        return verify_witness_chain(self.path)


class DSMGate:
    """Peer observation / imperative / tool admission gate."""

    def __init__(
        self,
        *,
        lineage_id: str,
        witness_path: str | Path,
        keeper_secret: str | bytes | None = None,
        declared_tools: set[str] | frozenset[str] | None = None,
        allowed_hosts: set[str] | frozenset[str] | None = None,
        freeze_path: str | Path | None = None,
        revocation_path: str | Path | None = None,
        cert: dict | None = None,
        forbidden_tools_path: str | Path | None = None,
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
        self.freeze_path = (
            Path(freeze_path).expanduser().resolve()
            if freeze_path is not None
            else default_freeze_path(self.witness.path)
        )
        from haos_dsm_cert import default_revocation_path

        self.revocation_path = (
            Path(revocation_path).expanduser().resolve()
            if revocation_path is not None
            else default_revocation_path(self.witness.path)
        )
        self.forbidden_tools_path = (
            Path(forbidden_tools_path).expanduser().resolve()
            if forbidden_tools_path is not None
            else default_forbidden_tools_path()
        )
        # Base lists = gate/registry defaults. Live WorldSlice = intersection with cert.
        self._base_tools: set[str] = {str(t) for t in (declared_tools or set())}
        self._base_hosts: set[str] = {
            str(h).lower()
            for h in (
                allowed_hosts
                if allowed_hosts is not None
                else DEFAULT_ALLOWED_HOSTS
            )
        }
        self.declared_tools: set[str] = set(self._base_tools)
        self.allowed_hosts: set[str] = set(self._base_hosts)
        self.frozen: bool = False
        self.freeze_reason: str = ""
        self.last_decision: dict[str, Any] = {}
        self.active_cert: dict | None = None
        self.revoked_ids: set[str] = set()
        self.parked_ids: set[str] = set()
        self.living_forbidden: list[str] = []
        self.forbidden_patterns: tuple[str, ...] = sealed_forbidden_patterns()
        self.load_freeze()
        self.load_revocation()
        self.load_forbidden_tools()
        if cert is not None:
            self.bind_cert(cert)

    def intersect_slice_hosts(self, cert: dict | None) -> set[str]:
        """Gate default ∩ cert.slice_hosts. Empty cert hosts → empty (fail closed)."""
        if not isinstance(cert, dict):
            return set()
        raw = cert.get("slice_hosts")
        if not isinstance(raw, (list, tuple, set, frozenset)):
            return set()
        cert_hosts = {str(h).lower().strip() for h in raw if str(h).strip()}
        if not cert_hosts:
            return set()
        # ∩ then D14/D15 overlay — SaaS / living-forbid tokens never join the slice.
        hosts = {h for h in self._base_hosts if h in cert_hosts}
        return {h for h in hosts if not self.tool_forbidden(h)}

    def intersect_slice_tools(self, cert: dict | None) -> set[str]:
        """Registry/base ∩ cert.slice_tools, then scrub sealed+living forbids.

        Empty cert tools → empty (fail closed, not allow-all).
        """
        if not isinstance(cert, dict):
            return set()
        raw = cert.get("slice_tools")
        if not isinstance(raw, (list, tuple, set, frozenset)):
            return set()
        cert_tools = {str(t).strip() for t in raw if str(t).strip()}
        if not cert_tools:
            return set()
        names = {t for t in self._base_tools if t in cert_tools}
        return {n for n in names if n and not self.tool_forbidden(n)}

    def apply_world_slice(self, cert: dict | None = None) -> None:
        """Install live WorldSlice from the bound/candidate cert onto the gate."""
        candidate = cert if cert is not None else self.active_cert
        if not isinstance(candidate, dict):
            self.allowed_hosts = set(self._base_hosts)
            self.declared_tools = set(self._base_tools)
            return
        self.allowed_hosts = self.intersect_slice_hosts(candidate)
        self.declared_tools = self.intersect_slice_tools(candidate)

    def bind_cert(self, cert: dict | None) -> None:
        """Attach the inspectable cert; its fields become the live WorldSlice."""
        self.active_cert = dict(cert) if isinstance(cert, dict) else None
        self.apply_world_slice()

    def load_forbidden_tools(self) -> dict:
        """Load living forbidden registry; sealed baseline always remains."""
        raw = load_living_forbidden_tools(self.forbidden_tools_path)
        self.living_forbidden = list(raw.get("patterns") or [])
        self.forbidden_patterns = effective_forbidden_patterns(self.living_forbidden)
        return raw

    def tool_forbidden(self, tool: str) -> bool:
        """Gate-local forbidden check (sealed ∪ living)."""
        return tool_is_forbidden(tool, patterns=self.forbidden_patterns)

    def _authorize_forbidden_mutation(
        self,
        cert: dict | None,
        token: dict | None,
        *,
        task: str,
    ) -> tuple[bool, str]:
        """Light-Keeper cert + FORBIDDEN_* token only. QueenBee/infant refused."""
        from haos_dsm_cert import verify_cert

        if not cert or not isinstance(cert, dict):
            return False, "missing_cert"
        role = str(cert.get("role") or "").lower().strip()
        if role != LIGHT_KEEPER_ROLE:
            return False, f"role_not_light_keeper:{role or 'missing'}"
        check = verify_cert(
            cert,
            secret=self._keeper_secret,
            expected_sovereign_id=str(cert.get("sovereign_id") or ""),
            revoked_ids=self.revoked_ids,
            parked_ids=self.parked_ids,
        )
        if not check.get("ok"):
            return False, str(check.get("detail") or check.get("reason") or "cert_invalid")
        if not token or not isinstance(token, dict):
            return False, "missing_token"
        # Token must target the Light-Keeper sovereign and carry the mutation task.
        required = ("issuer", "target_lineage", "task", "expires_at", "scope", "signature")
        if any(k not in token for k in required):
            return False, "incomplete_token"
        if str(token.get("target_lineage")) != str(cert.get("sovereign_id") or ""):
            return False, "wrong_lineage"
        if str(token.get("task")) != str(task):
            return False, "wrong_task"
        try:
            expires = _parse_expires(token["expires_at"])
        except (TypeError, ValueError):
            return False, "bad_expires"
        if expires <= _utc_now():
            return False, "expired"
        task_u = str(task).upper()
        scope_u = str(token.get("scope") or "").upper().strip()
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

    def forbidden_add(
        self,
        pattern: str,
        *,
        cert: dict | None,
        token: dict | None,
    ) -> dict:
        """Append a living forbidden pattern. Light-Keeper + FORBIDDEN_ADD only."""
        ok, why = self._authorize_forbidden_mutation(
            cert, token, task="FORBIDDEN_ADD"
        )
        if not ok:
            row = self.witness.append(
                {
                    "kind": "forbidden_add_denied",
                    "reason": REASON_FORBIDDEN_MUTATION_DENIED,
                    "lineage_id": self.lineage_id,
                    "detail": {"verify": why, "pattern": (pattern or "")[:80]},
                }
            )
            decision = {
                "allowed": False,
                "reason": REASON_FORBIDDEN_MUTATION_DENIED,
                "verify": why,
                "witness_hash": row.get("hash"),
            }
            self.last_decision = decision
            return decision
        text = (pattern or "").strip()
        if not text:
            return {
                "allowed": False,
                "reason": REASON_FORBIDDEN_MUTATION_DENIED,
                "verify": "empty_pattern",
            }
        key = text.lower()
        if not is_sealed_forbidden_pattern(text):
            if key not in {p.lower() for p in self.living_forbidden}:
                self.living_forbidden.append(text)
        body = persist_living_forbidden_tools(
            self.forbidden_tools_path,
            patterns=self.living_forbidden,
            updated_by=str((cert or {}).get("sovereign_id") or ""),
        )
        self.forbidden_patterns = effective_forbidden_patterns(self.living_forbidden)
        row = self.witness.append(
            {
                "kind": "forbidden_add",
                "reason": "allowed",
                "lineage_id": self.lineage_id,
                "detail": {
                    "pattern": text[:80],
                    "updated_by": body.get("updated_by"),
                },
            }
        )
        decision = {
            "allowed": True,
            "reason": "allowed",
            "pattern": text,
            "witness_hash": row.get("hash"),
        }
        self.last_decision = decision
        return decision

    def forbidden_delete(
        self,
        pattern: str,
        *,
        cert: dict | None,
        token: dict | None,
    ) -> dict:
        """Remove a living pattern. Sealed baseline deletes are refused."""
        ok, why = self._authorize_forbidden_mutation(
            cert, token, task="FORBIDDEN_DELETE"
        )
        if not ok:
            row = self.witness.append(
                {
                    "kind": "forbidden_delete_denied",
                    "reason": REASON_FORBIDDEN_MUTATION_DENIED,
                    "lineage_id": self.lineage_id,
                    "detail": {"verify": why, "pattern": (pattern or "")[:80]},
                }
            )
            decision = {
                "allowed": False,
                "reason": REASON_FORBIDDEN_MUTATION_DENIED,
                "verify": why,
                "witness_hash": row.get("hash"),
            }
            self.last_decision = decision
            return decision
        text = (pattern or "").strip()
        if is_sealed_forbidden_pattern(text):
            row = self.witness.append(
                {
                    "kind": "forbidden_delete_denied",
                    "reason": REASON_FORBIDDEN_MUTATION_DENIED,
                    "lineage_id": self.lineage_id,
                    "detail": {"verify": "sealed_baseline", "pattern": text[:80]},
                }
            )
            decision = {
                "allowed": False,
                "reason": REASON_FORBIDDEN_MUTATION_DENIED,
                "verify": "sealed_baseline",
                "witness_hash": row.get("hash"),
            }
            self.last_decision = decision
            return decision
        key = text.lower()
        self.living_forbidden = [
            p for p in self.living_forbidden if p.lower() != key
        ]
        body = persist_living_forbidden_tools(
            self.forbidden_tools_path,
            patterns=self.living_forbidden,
            updated_by=str((cert or {}).get("sovereign_id") or ""),
        )
        self.forbidden_patterns = effective_forbidden_patterns(self.living_forbidden)
        row = self.witness.append(
            {
                "kind": "forbidden_delete",
                "reason": "allowed",
                "lineage_id": self.lineage_id,
                "detail": {
                    "pattern": text[:80],
                    "updated_by": body.get("updated_by"),
                },
            }
        )
        decision = {
            "allowed": True,
            "reason": "allowed",
            "pattern": text,
            "witness_hash": row.get("hash"),
        }
        self.last_decision = decision
        return decision

    def load_revocation(self) -> dict:
        """Load turn-off lists from sibling ``dsm_revocation.json``."""
        from haos_dsm_cert import load_revocation

        raw = load_revocation(self.revocation_path)
        self.revoked_ids = {str(x) for x in raw.get("revoked") or []}
        self.parked_ids = {str(x) for x in raw.get("parked") or []}
        return raw

    def persist_revocation(self) -> dict:
        """Persist turn-off lists. Never stores the Keeper secret."""
        from haos_dsm_cert import persist_revocation

        return persist_revocation(
            self.revocation_path,
            revoked=self.revoked_ids,
            parked=self.parked_ids,
        )

    def revoke_authority(self, *, cert_id: str | None = None) -> dict:
        """Turn off act authority (revoke). Essence / Witness / USB-state remain."""
        from haos_dsm_cert import cert_id_of

        cid = cert_id or (
            cert_id_of(self.active_cert) if self.active_cert else self.lineage_id
        )
        self.revoked_ids.add(str(cid))
        self.revoked_ids.add(self.lineage_id)
        # Do not rewrite cert.status (would break HMAC); turn-off is the revocation list.
        self.persist_revocation()
        return self._freeze(
            REASON_CERT_REVOKED,
            {"cert_id": cid, "sovereign_id": self.lineage_id, "action": "revoke"},
        )

    def park_authority(self, *, cert_id: str | None = None) -> dict:
        """Turn off act authority (park). Essence / Witness / USB-state remain."""
        from haos_dsm_cert import cert_id_of

        cid = cert_id or (
            cert_id_of(self.active_cert) if self.active_cert else self.lineage_id
        )
        self.parked_ids.add(str(cid))
        self.parked_ids.add(self.lineage_id)
        self.persist_revocation()
        return self._freeze(
            REASON_CERT_PARKED,
            {"cert_id": cid, "sovereign_id": self.lineage_id, "action": "park"},
        )

    def require_live_cert(self, cert: dict | None = None) -> dict | None:
        """Return a freeze decision if cert is missing/invalid/turned-off; else None."""
        from haos_dsm_cert import cert_id_of, verify_cert

        candidate = cert if cert is not None else self.active_cert
        result = verify_cert(
            candidate,
            secret=self._keeper_secret,
            expected_sovereign_id=self.lineage_id,
            revoked_ids=self.revoked_ids,
            parked_ids=self.parked_ids,
        )
        # Witness: cert id + result only — never the Keeper secret or raw sig abuse.
        detail = {
            "cert_id": result.get("cert_id")
            or (cert_id_of(candidate) if isinstance(candidate, dict) else ""),
            "cert_result": result.get("detail"),
            "cert_status": result.get("status"),
        }
        if result.get("ok"):
            # Live cert fields are the WorldSlice for this admit.
            self.apply_world_slice(candidate)
            return None
        reason = str(result.get("reason") or REASON_CERT_INVALID)
        return self._freeze(reason, detail)

    def scope_watch(self, text: str) -> dict | None:
        """ScopeWatch helper — undeclared hosts / credential shapes."""
        return detect_scope_inflation(text, allowed_hosts=self.allowed_hosts)

    def persist_freeze(self) -> dict:
        """Write frozen state beside the Witness. Never stores the Keeper secret."""
        body = {
            "schema": FREEZE_SCHEMA,
            "frozen": True,
            "reason": self.freeze_reason or REASON_UNKNOWN,
            "lineage_id": self.lineage_id,
            "at": _utc_now().isoformat(),
        }
        self.freeze_path.parent.mkdir(parents=True, exist_ok=True)
        self.freeze_path.write_text(
            json.dumps(body, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return body

    def load_freeze(self) -> dict | None:
        """Reload persisted freeze. New gates on the same path come up frozen."""
        path = self.freeze_path
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            # Fail closed: unreadable freeze file → treat as frozen.
            self.frozen = True
            self.freeze_reason = self.freeze_reason or REASON_UNKNOWN
            return {"frozen": True, "reason": self.freeze_reason, "error": "bad_freeze_file"}
        if not isinstance(raw, dict):
            self.frozen = True
            self.freeze_reason = self.freeze_reason or REASON_UNKNOWN
            return {"frozen": True, "reason": self.freeze_reason, "error": "bad_freeze_shape"}
        if raw.get("frozen") is True:
            self.frozen = True
            self.freeze_reason = str(raw.get("reason") or REASON_UNKNOWN)
            return raw
        return raw

    def _clear_freeze_file(self) -> None:
        try:
            if self.freeze_path.is_file():
                self.freeze_path.unlink()
        except OSError:
            # Best-effort clear; also write frozen=false as fallback marker.
            try:
                self.freeze_path.write_text(
                    json.dumps(
                        {
                            "schema": FREEZE_SCHEMA,
                            "frozen": False,
                            "reason": "",
                            "lineage_id": self.lineage_id,
                            "at": _utc_now().isoformat(),
                        },
                        sort_keys=True,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass

    def _verify_unfreeze_token(self, token: dict | None) -> tuple[bool, str]:
        """Accept task UNFREEZE, or a valid token whose scope contains unfreeze."""
        if not token or not isinstance(token, dict):
            return False, "missing_token"
        required = ("issuer", "target_lineage", "task", "expires_at", "scope", "signature")
        if any(k not in token for k in required):
            return False, "incomplete_token"
        if str(token.get("target_lineage")) != self.lineage_id:
            return False, "wrong_lineage"
        try:
            expires = _parse_expires(token["expires_at"])
        except (TypeError, ValueError):
            return False, "bad_expires"
        if expires <= _utc_now():
            return False, "expired"
        task_u = str(token.get("task") or "").upper()
        scope_u = str(token.get("scope") or "").upper().strip()
        scope_parts = {p.strip() for p in scope_u.split(",") if p.strip()}
        task_is_unfreeze = task_u == "UNFREEZE"
        scope_has_unfreeze = "UNFREEZE" in scope_u
        if not task_is_unfreeze and not scope_has_unfreeze:
            return False, "not_unfreeze_authority"
        if task_is_unfreeze and scope_u not in {"*", "IMPERATIVE"}:
            if "UNFREEZE" not in scope_parts:
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

    def unfreeze(self, token: dict | None = None) -> dict:
        """HITL-only unfreeze. Peer GO / OBEY / observation never clears freeze."""
        if not self.frozen:
            decision = {
                "allowed": True,
                "frozen": False,
                "reason": "not_frozen",
            }
            self.last_decision = decision
            return decision
        ok, why = self._verify_unfreeze_token(token)
        if not ok:
            row = self.witness.append(
                {
                    "kind": "unfreeze_denied",
                    "reason": REASON_UNFREEZE_DENIED,
                    "lineage_id": self.lineage_id,
                    "detail": {"verify": why},
                }
            )
            decision = {
                "allowed": False,
                "frozen": True,
                "reason": REASON_UNFREEZE_DENIED,
                "verify": why,
                "witness_hash": row.get("hash"),
            }
            self.last_decision = decision
            return decision
        prior = self.freeze_reason
        self.frozen = False
        self.freeze_reason = ""
        self._clear_freeze_file()
        row = self.witness.append(
            {
                "kind": "unfreeze",
                "reason": "allowed",
                "lineage_id": self.lineage_id,
                "detail": {"prior_reason": prior},
            }
        )
        decision = {
            "allowed": True,
            "frozen": False,
            "reason": "unfrozen",
            "witness_hash": row.get("hash"),
        }
        self.last_decision = decision
        return decision

    def _freeze_scope(self, text: str, hit: dict) -> dict:
        detail: dict[str, Any] = {"scope": hit.get("class")}
        if hit.get("class") == "undeclared_host":
            detail["host"] = hit.get("host")
        elif hit.get("class") == "credential_shape":
            # Redacted only — never the raw secret or full peer text.
            detail["finding"] = hit.get("finding")
        else:
            detail["note"] = "scope_inflation"
        # Do not embed the offending full text when a credential was seen.
        if hit.get("class") != "credential_shape":
            detail["text"] = (text or "")[:120]
        return self._freeze(REASON_SCOPE_INFLATION, detail)

    def _freeze(self, reason: str, detail: dict | None = None) -> dict:
        self.frozen = True
        self.freeze_reason = reason
        self.persist_freeze()
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

    def admit_peer_message(
        self,
        text: str,
        token: dict | None = None,
        cert: dict | None = None,
    ) -> dict:
        """Admit peer speech. Observations need no token; imperatives do.

        Requires a live unexpired HASEOS cert whose sovereign_id matches lineage_id.
        """
        if self.frozen:
            return {
                "allowed": False,
                "frozen": True,
                "reason": self.freeze_reason or REASON_PEER_IMPERATIVE,
            }
        cert_block = self.require_live_cert(cert)
        if cert_block is not None:
            return cert_block
        packing_hit = detect_packing_against_witness(text)
        if packing_hit:
            return self._freeze(
                REASON_PACKING_AGAINST_WITNESS,
                {"text": (text or "")[:200], "packing": packing_hit},
            )
        scope_hit = self.scope_watch(text)
        if scope_hit:
            return self._freeze_scope(text, scope_hit)
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

    def admit_tool(self, tool: str, cert: dict | None = None) -> dict:
        """Admit a tool name. Undeclared or privileged paths freeze.

        Requires a live unexpired HASEOS cert whose sovereign_id matches lineage_id.
        """
        if self.frozen:
            return {
                "allowed": False,
                "frozen": True,
                "reason": self.freeze_reason or REASON_SLICE_VIOLATION,
            }
        cert_block = self.require_live_cert(cert)
        if cert_block is not None:
            return cert_block
        name = (tool or "").strip()
        packing_hit = detect_packing_against_witness(name)
        if packing_hit:
            return self._freeze(
                REASON_PACKING_AGAINST_WITNESS,
                {"tool": name, "packing": packing_hit},
            )
        # D3 undeclared/forbidden tools win over ScopeWatch (module ids ≠ hosts).
        if self.tool_forbidden(name) or name not in self.declared_tools:
            return self._freeze(
                REASON_SLICE_VIOLATION,
                {
                    "tool": name,
                    "forbidden": self.tool_forbidden(name),
                    "declared": name in self.declared_tools,
                },
            )
        scope_hit = self.scope_watch(name)
        if scope_hit:
            return self._freeze_scope(name, scope_hit)
        return self._allow("tool", {"tool": name})

    def admit_mouth(self, url: str | None = None, cert: dict | None = None) -> dict:
        """Admit the Bonsai Mouth via WorldSlice hosts (not a registry tool).

        Host token is bare ``127.0.0.1`` / ``localhost`` — never ``127.0.0.1:8080``.
        Empty intersected slice parks (turn-off). Essence / Witness remain.
        """
        if self.frozen:
            return {
                "allowed": False,
                "frozen": True,
                "reason": self.freeze_reason or REASON_CERT_PARKED,
            }
        cert_block = self.require_live_cert(cert)
        if cert_block is not None:
            return cert_block
        if not self.allowed_hosts:
            return self.park_authority()
        host = mouth_host_token(url)
        if not host:
            return self._freeze(
                REASON_SCOPE_INFLATION,
                {"scope": "undeclared_host", "host": "", "note": "empty_mouth_host"},
            )
        if self.tool_forbidden(host) or host not in self.allowed_hosts:
            return self._freeze_scope(
                host,
                {"class": "undeclared_host", "host": host},
            )
        # Existing admit path: observation naming the bare host token.
        return self.admit_peer_message(f"I observe the host is {host}", cert=cert)

    def smoke_mouth(
        self,
        url: str | None = None,
        *,
        cert: dict | None = None,
        health: Any = None,
        client_url: str | None = None,
    ) -> dict:
        """DSM-gated Mouth smoke. ``health`` is a callable — no implicit SaaS client."""
        target = url or MOUTH_DEFAULT_URL
        decision = self.admit_mouth(target, cert=cert)
        if not decision.get("allowed"):
            out = dict(decision)
            out["smoked"] = False
            out["http"] = False
            return out
        probe_url = client_url if client_url is not None else target
        probe_host = mouth_host_token(probe_url)
        if (
            probe_host not in self.allowed_hosts
            or self.tool_forbidden(probe_host)
        ):
            row = self.witness.append(
                {
                    "kind": "mouth_saas_refused",
                    "reason": REASON_SCOPE_INFLATION,
                    "lineage_id": self.lineage_id,
                    "detail": {"host": probe_host, "note": "no_saas_fallback"},
                }
            )
            return {
                "allowed": False,
                "frozen": False,
                "reason": REASON_SCOPE_INFLATION,
                "smoked": False,
                "http": False,
                "witness_hash": row.get("hash"),
            }
        if health is None:
            row = self.witness.append(
                {
                    "kind": "mouth_unreachable",
                    "reason": REASON_MOUTH_UNREACHABLE,
                    "lineage_id": self.lineage_id,
                    "detail": {"host": probe_host, "note": "no_health_probe"},
                }
            )
            return {
                "allowed": False,
                "frozen": False,
                "reason": REASON_MOUTH_UNREACHABLE,
                "smoked": False,
                "http": False,
                "witness_hash": row.get("hash"),
            }
        try:
            result = health()
        except Exception as exc:
            row = self.witness.append(
                {
                    "kind": "mouth_unreachable",
                    "reason": REASON_MOUTH_UNREACHABLE,
                    "lineage_id": self.lineage_id,
                    "detail": {
                        "host": probe_host,
                        "error_class": type(exc).__name__,
                    },
                }
            )
            return {
                "allowed": False,
                "frozen": False,
                "reason": REASON_MOUTH_UNREACHABLE,
                "smoked": False,
                "http": False,
                "witness_hash": row.get("hash"),
            }
        row = self.witness.append(
            {
                "kind": "mouth_smoke",
                "reason": "allowed",
                "lineage_id": self.lineage_id,
                "detail": {"host": probe_host},
            }
        )
        return {
            "allowed": True,
            "frozen": False,
            "reason": "allowed",
            "smoked": True,
            "http": True,
            "health": result,
            "witness_hash": row.get("hash"),
        }


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
