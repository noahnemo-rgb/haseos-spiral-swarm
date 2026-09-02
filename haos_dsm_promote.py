#!/usr/bin/env python3
"""D22 — HITL /promote writes a Senior or Infant cert beside USB.

QueenBee may propose sovereign_id / role / slice only.
Light-Keeper HMAC secret comes from HASEOS_KEEPER_SECRET in the env.
Never import queenbee_integration (that pulls torch).
This drop does not mint Chief of Staff or Supervisor/QC.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from haos_dsm_cert import cert_id_of
from haos_dsm_infant import INFANT_CERT_FILENAME
from haos_dsm_senior import SENIOR_CERT_FILENAME

SECRET_ENV = "HASEOS_KEEPER_SECRET"
REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SENIOR_CERT = "dsm_cert_senior.json"
DEFAULT_QUEENBEE_CERT = "dsm_cert_queenbee.json"
DEFAULT_ROLE = "infant"
DEFAULT_HOSTS = ("localhost", "127.0.0.1")
DEFAULT_TOOLS = ("status",)

REASON_SECRET_MISSING = "SECRET_MISSING"
REASON_SENIOR_CERT_MISSING = "SENIOR_CERT_MISSING"
REASON_QUEENBEE_CERT_MISSING = "QUEENBEE_CERT_MISSING"
REASON_SLICE_NOT_SUBSET = "SLICE_NOT_SUBSET"
REASON_ROLE_REFUSED = "ROLE_REFUSED"
REASON_SOVEREIGN_MISSING = "SOVEREIGN_ID_REQUIRED"
REASON_INIT_REFUSED = "INIT_REFUSED"

REFUSED_ROLES = frozenset(
    {
        "chief-of-staff",
        "supervisor-qc",
        "queenbee",
        "light-keeper",
    }
)

_SCRIPT_CACHE: dict[str, Any] = {}


def _fail(reason: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "cert_written": False}


def _load_init_script(name: str) -> Any:
    cached = _SCRIPT_CACHE.get(name)
    if cached is not None:
        return cached
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _SCRIPT_CACHE[name] = mod
    return mod


def _secret_from(environ: dict[str, str] | None) -> str | None:
    env = environ if environ is not None else os.environ
    raw = env.get(SECRET_ENV)
    if raw is None or not str(raw).strip():
        return None
    return str(raw)


def _existing_cert_path(
    explicit: str | Path | None,
    *,
    default_name: str,
    repo_root: Path,
) -> Path | None:
    if explicit is not None:
        dest = Path(explicit)
        return dest if dest.is_file() else None
    dest = repo_root / default_name
    return dest if dest.is_file() else None


def _map_init_error(exc: BaseException) -> str:
    text = str(exc)
    if "⊆" in text:
        return REASON_SLICE_NOT_SUBSET
    if "HASEOS_KEEPER_SECRET" in text:
        return REASON_SECRET_MISSING
    return REASON_INIT_REFUSED


def _store_reason_note(usb_image: str | Path | None, reason: str | None) -> None:
    """HITL reason as USB note text only — not signing authority. Never the secret."""
    if not reason or usb_image is None:
        return
    image = Path(usb_image)
    if not image.is_file():
        return
    import usb_state

    state = usb_state.load(image)
    notes = state.get("notes")
    if not isinstance(notes, dict):
        notes = {}
        state["notes"] = notes
    notes["dsm_promote_reason"] = str(reason)
    usb_state.save(state, image)


def promote_to_usb_cert(
    *,
    sovereign_id: str,
    role: str = DEFAULT_ROLE,
    reason: str | None = None,
    senior_cert_path: str | Path | None = None,
    queenbee_cert_path: str | Path | None = None,
    usb_image: str | Path | None = None,
    out_path: str | Path | None = None,
    hosts: list[str] | None = None,
    tools: list[str] | None = None,
    environ: dict[str, str] | None = None,
    repo_root: str | Path | None = None,
    primary_witness: str | Path | None = None,
) -> dict[str, Any]:
    """Mint infant or senior cert. Never raises through QueenBee. Never returns the secret."""
    sid = (sovereign_id or "").strip()
    if not sid:
        return _fail(REASON_SOVEREIGN_MISSING)
    role_s = (role or DEFAULT_ROLE).strip().lower() or DEFAULT_ROLE
    if role_s in REFUSED_ROLES:
        return _fail(REASON_ROLE_REFUSED)
    if role_s not in {"infant", "senior"}:
        return _fail(REASON_ROLE_REFUSED)
    if _secret_from(environ) is None:
        return _fail(REASON_SECRET_MISSING)

    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    filename = SENIOR_CERT_FILENAME if role_s == "senior" else INFANT_CERT_FILENAME
    if out_path is not None:
        dest = Path(out_path)
    elif usb_image is not None:
        dest = Path(usb_image).parent / filename
    else:
        dest = root / filename

    slice_hosts = list(hosts) if hosts is not None else list(DEFAULT_HOSTS)
    slice_tools = list(tools) if tools is not None else list(DEFAULT_TOOLS)

    try:
        if role_s == "infant":
            senior = _existing_cert_path(
                senior_cert_path,
                default_name=DEFAULT_SENIOR_CERT,
                repo_root=root,
            )
            if senior is None:
                return _fail(REASON_SENIOR_CERT_MISSING)
            qb = _existing_cert_path(
                queenbee_cert_path,
                default_name=DEFAULT_QUEENBEE_CERT,
                repo_root=root,
            )
            infant_mod = _load_init_script("init_infant_cert")
            cert = infant_mod.init_infant_cert(
                sovereign_id=sid,
                senior_cert_path=senior,
                queenbee_cert_path=qb,
                out_path=dest,
                hosts=slice_hosts,
                tools=slice_tools,
                usb_image=usb_image,
                primary_witness=primary_witness,
                environ=environ,
                write_file=True,
            )
        else:
            qb = _existing_cert_path(
                queenbee_cert_path,
                default_name=DEFAULT_QUEENBEE_CERT,
                repo_root=root,
            )
            if qb is None:
                return _fail(REASON_QUEENBEE_CERT_MISSING)
            senior_mod = _load_init_script("init_senior_cert")
            cert = senior_mod.init_senior_cert(
                sovereign_id=sid,
                queenbee_cert_path=qb,
                out_path=dest,
                hosts=slice_hosts,
                tools=slice_tools,
                usb_image=usb_image,
                primary_witness=primary_witness,
                environ=environ,
                write_file=True,
            )
    except Exception as exc:
        return _fail(_map_init_error(exc))

    _store_reason_note(usb_image, reason)
    return {
        "ok": True,
        "role": role_s,
        "dest": str(dest),
        "cert_id": cert_id_of(cert),
        "cert_written": True,
    }
