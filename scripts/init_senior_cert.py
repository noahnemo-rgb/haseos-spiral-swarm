#!/usr/bin/env python3
"""Senior cert at HITL promotion — minted by Light-Keeper on the AX-18.

QueenBee may propose sovereign_id / slice fields. The Keeper secret stays in
the local env only — never on QueenBee, USB infants, or git.
Senior WorldSlice must be ⊆ QueenBee WorldSlice when --queenbee-cert is given.
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
from haos_dsm_senior import (  # noqa: E402
    SENIOR_CERT_FILENAME,
    place_senior_cert_beside_usb,
    senior_slice_fits_queenbee,
)

SECRET_ENV = "HASEOS_KEEPER_SECRET"
DEFAULT_OUT = "dsm_cert_senior.json"
DEFAULT_ISSUER = "Light-Keeper"
DEFAULT_ROLE = "senior"
DEFAULT_HOSTS = ("localhost", "127.0.0.1")
DEFAULT_TOOLS = ("status",)
DEFAULT_HOURS = 24.0 * 365


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


def load_queenbee_cert(path: str | Path) -> dict:
    dest = Path(path)
    if not dest.is_file():
        raise InitError(f"--queenbee-cert not found: {dest}")
    try:
        raw = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InitError(f"--queenbee-cert unreadable: {dest}") from exc
    if not isinstance(raw, dict):
        raise InitError("--queenbee-cert must be a JSON object")
    return raw


def init_senior_cert(
    *,
    sovereign_id: str,
    out_path: str | Path = DEFAULT_OUT,
    hours: float = DEFAULT_HOURS,
    issuer: str = DEFAULT_ISSUER,
    role: str = DEFAULT_ROLE,
    hosts: list[str] | None = None,
    tools: list[str] | None = None,
    queenbee_cert: dict | None = None,
    queenbee_cert_path: str | Path | None = None,
    usb_image: str | Path | None = None,
    primary_witness: str | Path | None = None,
    secret: str | None = None,
    environ: dict[str, str] | None = None,
    write_file: bool = True,
) -> dict:
    """Mint a live senior cert. Never writes the Keeper secret."""
    sid = (sovereign_id or "").strip()
    if not sid:
        raise InitError("--sovereign-id is required")
    role_s = (role or DEFAULT_ROLE).strip().lower() or DEFAULT_ROLE
    if role_s == "infant":
        raise InitError("role=infant is D19 — refused in this drop")
    if role_s != DEFAULT_ROLE:
        raise InitError(f"role must be {DEFAULT_ROLE} (got {role_s})")
    if hours <= 0:
        raise InitError("--hours must be positive")
    key = secret if secret is not None else read_keeper_secret(environ)
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
    qb = queenbee_cert
    if qb is None and queenbee_cert_path is not None:
        qb = load_queenbee_cert(queenbee_cert_path)
    if qb is not None and not senior_slice_fits_queenbee(proposed, qb):
        raise InitError(
            "senior WorldSlice is not ⊆ QueenBee WorldSlice "
            "(empty senior lists fail closed)"
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
            place_senior_cert_beside_usb(
                usb_image,
                cert,
                primary_witness=primary_witness,
            )
    return cert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mint a Senior HASEOS cert at HITL promotion (Light-Keeper)."
    )
    parser.add_argument(
        "--sovereign-id",
        required=True,
        help="Senior sovereign id (HITL / QueenBee-proposed)",
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
        help=f"Must be {DEFAULT_ROLE}; infant is D19",
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
        "--queenbee-cert",
        default=None,
        help="Existing QueenBee cert JSON; senior slice must be ⊆ that slice",
    )
    parser.add_argument(
        "--usb-image",
        default=None,
        help="USB-state JSON; writes dsm_cert_senior.json beside it",
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
        cert = init_senior_cert(
            sovereign_id=args.sovereign_id,
            out_path=args.out,
            hours=args.hours,
            issuer=args.issuer,
            role=args.role,
            hosts=args.hosts,
            tools=args.tools,
            queenbee_cert_path=args.queenbee_cert,
            usb_image=args.usb_image,
            primary_witness=args.primary_witness,
        )
    except InitError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(cert, sort_keys=True, indent=2) + "\n")
    print(f"wrote {args.out}", file=sys.stderr)
    if args.usb_image:
        print(f"usb cert {SENIOR_CERT_FILENAME}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
