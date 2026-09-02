#!/usr/bin/env python3
"""Team Leading Supervisor/QC cert — minted by Light-Keeper on the AX-18 (HITL).

The Keeper secret stays in the local env only.
Supervisor WorldSlice must be ⊆ Chief of Staff WorldSlice (--chief-cert required).
Optional --lightkeeper-cert also requires supervisor ⊆ Light-Keeper.
QueenBee does not mint this and must not read .haseos_keeper.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from haos_dsm_cert import CERT_STATUS_LIVE, mint_haseos_cert  # noqa: E402
from haos_dsm_supervisor import (  # noqa: E402
    SUPERVISOR_CERT_FILENAME,
    supervisor_slice_fits_chief,
    place_supervisor_cert_beside_usb,
)

SECRET_ENV = "HASEOS_KEEPER_SECRET"
DEFAULT_OUT = "dsm_cert_supervisor_qc.json"
DEFAULT_ISSUER = "Light-Keeper"
DEFAULT_ROLE = "supervisor-qc"
DEFAULT_HOSTS = ("localhost", "127.0.0.1")
DEFAULT_TOOLS = ("status",)
DEFAULT_HOURS = 24.0 * 365
REFUSED_ROLES = {
    "chief-of-staff": "D20",
    "infant": "D19",
    "senior": "D18",
    "queenbee": "D13",
    "light-keeper": "D12",
}


class InitError(RuntimeError):
    """User-facing init failure."""


def missing_secret_help() -> str:
    return (
        f"{SECRET_ENV} is missing or empty.\n"
        "Export it from your local Light-Keeper shell only, e.g.:\n"
        f"  export {SECRET_ENV}=$(cat .haseos_keeper)\n"
        "(Do not commit .haseos_keeper or paste the value into git/chat.)"
    )


def read_keeper_secret(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    raw = env.get(SECRET_ENV)
    if raw is None or not str(raw).strip():
        raise InitError(missing_secret_help())
    return str(raw)


def load_cert_json(path: str | Path, *, flag: str) -> dict:
    dest = Path(path)
    if not dest.is_file():
        raise InitError(f"{flag} not found: {dest}")
    try:
        raw = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InitError(f"{flag} unreadable: {dest}") from exc
    if not isinstance(raw, dict):
        raise InitError(f"{flag} must be a JSON object")
    return raw


def init_supervisor_qc_cert(
    *,
    sovereign_id: str,
    chief_cert: dict | None = None,
    chief_cert_path: str | Path | None = None,
    lightkeeper_cert: dict | None = None,
    lightkeeper_cert_path: str | Path | None = None,
    out_path: str | Path = DEFAULT_OUT,
    hours: float = DEFAULT_HOURS,
    issuer: str = DEFAULT_ISSUER,
    role: str = DEFAULT_ROLE,
    hosts: list[str] | None = None,
    tools: list[str] | None = None,
    usb_image: str | Path | None = None,
    primary_witness: str | Path | None = None,
    secret: str | None = None,
    environ: dict[str, str] | None = None,
    write_file: bool = True,
) -> dict:
    """Mint a live supervisor-qc cert. Never writes the Keeper secret."""
    sid = (sovereign_id or "").strip()
    if not sid:
        raise InitError("--sovereign-id is required")
    role_s = (role or DEFAULT_ROLE).strip().lower() or DEFAULT_ROLE
    if role_s in REFUSED_ROLES:
        raise InitError(f"role={role_s} is {REFUSED_ROLES[role_s]} — refused in this drop")
    if role_s != DEFAULT_ROLE:
        raise InitError(f"role must be {DEFAULT_ROLE} (got {role_s})")
    if hours <= 0:
        raise InitError("--hours must be positive")
    key = secret if secret is not None else read_keeper_secret(environ)
    chief = chief_cert
    if chief is None:
        if chief_cert_path is None:
            raise InitError("--chief-cert is required")
        chief = load_cert_json(chief_cert_path, flag="--chief-cert")
    if hosts is None:
        slice_hosts: list[str] = list(DEFAULT_HOSTS)
    else:
        slice_hosts = [str(h).strip() for h in hosts]
    if tools is None:
        slice_tools = list(DEFAULT_TOOLS)
    else:
        slice_tools = [str(t).strip() for t in tools if str(t).strip()]
    proposed = {
        "slice_hosts": slice_hosts,
        "slice_tools": slice_tools,
    }
    keeper = lightkeeper_cert
    if keeper is None and lightkeeper_cert_path is not None:
        keeper = load_cert_json(lightkeeper_cert_path, flag="--lightkeeper-cert")
    if not supervisor_slice_fits_chief(proposed, chief):
        raise InitError(
            "supervisor WorldSlice is not ⊆ Chief of Staff WorldSlice "
            "(empty supervisor lists fail closed)"
        )
    if keeper is not None and not supervisor_slice_fits_chief(proposed, keeper):
        raise InitError(
            "supervisor WorldSlice is not ⊆ Light-Keeper WorldSlice "
            "(empty supervisor lists fail closed)"
        )
    cert = mint_haseos_cert(
        secret=key,
        sovereign_id=sid,
        role=DEFAULT_ROLE,
        slice_hosts=slice_hosts,
        slice_tools=slice_tools,
        issuer=(issuer or DEFAULT_ISSUER).strip() or DEFAULT_ISSUER,
        status=CERT_STATUS_LIVE,
        hours=float(hours),
    )
    if write_file:
        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(cert, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if usb_image is not None:
            place_supervisor_cert_beside_usb(
                usb_image,
                cert,
                primary_witness=primary_witness,
            )
    return cert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mint a Team Leading Supervisor/QC HASEOS cert (Light-Keeper HITL)."
    )
    parser.add_argument(
        "--sovereign-id",
        required=True,
        help="Supervisor/QC sovereign id (HITL-chosen)",
    )
    parser.add_argument(
        "--chief-cert",
        required=True,
        help="Existing Chief of Staff cert JSON; supervisor slice must be ⊆ that slice",
    )
    parser.add_argument(
        "--lightkeeper-cert",
        default=None,
        help="Optional Light-Keeper cert JSON; supervisor slice must also be ⊆ that slice",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"Cert JSON path (default {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=DEFAULT_HOURS,
        help=f"Hours until expiry (default {DEFAULT_HOURS})",
    )
    parser.add_argument("--issuer", default=DEFAULT_ISSUER)
    parser.add_argument(
        "--role",
        default=DEFAULT_ROLE,
        help=f"Must be {DEFAULT_ROLE}; chief-of-staff is D20",
    )
    parser.add_argument(
        "--host",
        action="append",
        dest="hosts",
        default=None,
        help="slice_hosts entry (repeatable; default localhost + 127.0.0.1)",
    )
    parser.add_argument(
        "--tool",
        action="append",
        dest="tools",
        default=None,
        help="slice_tools entry (repeatable; default: status)",
    )
    parser.add_argument(
        "--usb-image",
        default=None,
        help="USB-state JSON; writes dsm_cert_supervisor_qc.json beside it",
    )
    parser.add_argument(
        "--primary-witness",
        default=None,
        help="Optional primary Witness JSONL to copy beside the USB image",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cert = init_supervisor_qc_cert(
            sovereign_id=args.sovereign_id,
            chief_cert_path=args.chief_cert,
            lightkeeper_cert_path=args.lightkeeper_cert,
            out_path=args.out,
            hours=args.hours,
            issuer=args.issuer,
            role=args.role,
            hosts=args.hosts,
            tools=args.tools,
            usb_image=args.usb_image,
            primary_witness=args.primary_witness,
        )
    except InitError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(cert, sort_keys=True, indent=2) + "\n")
    print(f"wrote {args.out}", file=sys.stderr)
    if args.usb_image:
        print(f"usb cert {SUPERVISOR_CERT_FILENAME}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
