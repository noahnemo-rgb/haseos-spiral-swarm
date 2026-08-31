#!/usr/bin/env python3
"""First Light-Keeper on the AX-18 — mint a live inspectable cert (HITL).

Requires --sovereign-id. Reads HASEOS_KEEPER_SECRET from the environment only.
Never writes or prints the Keeper secret. Turn-off authority later is revoke/park,
not destruction of essence / Witness / USB-state.
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

from haos_dsm_cert import (  # noqa: E402
    CERT_STATUS_LIVE,
    mint_haseos_cert,
)

SECRET_ENV = "HASEOS_KEEPER_SECRET"
DEFAULT_OUT = "dsm_cert_lightkeeper.json"
DEFAULT_ISSUER = "Light-Keeper"
DEFAULT_ROLE = "light-keeper"
DEFAULT_HOSTS = ("localhost", "127.0.0.1")
DEFAULT_TOOLS = ("status",)
DEFAULT_HOURS = 24.0 * 365  # one year; HITL may pass --hours


class InitError(RuntimeError):
    """User-facing init failure."""


def missing_secret_help() -> str:
    """How to generate a local secret — instructions only, no live value."""
    return (
        f"{SECRET_ENV} is missing or empty.\n"
        "Generate one locally in your shell (do not paste it into git or chat):\n"
        "  python3 -c \"import secrets; print(secrets.token_hex(32))\"\n"
        f"Then:\n"
        f"  export {SECRET_ENV}=<that-value>\n"
        "Keep it only in your local environment or a gitignored env file."
    )


def read_keeper_secret(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    raw = env.get(SECRET_ENV)
    if raw is None or not str(raw).strip():
        raise InitError(missing_secret_help())
    return str(raw)


def init_light_keeper_cert(
    *,
    sovereign_id: str,
    out_path: str | Path = DEFAULT_OUT,
    hours: float = DEFAULT_HOURS,
    issuer: str = DEFAULT_ISSUER,
    tools: list[str] | None = None,
    secret: str | None = None,
    environ: dict[str, str] | None = None,
    write_file: bool = True,
) -> dict:
    """Mint a live light-keeper cert. Never writes the secret."""
    sid = (sovereign_id or "").strip()
    if not sid:
        raise InitError("--sovereign-id is required")
    if hours <= 0:
        raise InitError("--hours must be positive")
    key = secret if secret is not None else read_keeper_secret(environ)
    slice_tools = list(tools) if tools is not None else list(DEFAULT_TOOLS)
    cert = mint_haseos_cert(
        secret=key,
        sovereign_id=sid,
        role=DEFAULT_ROLE,
        slice_hosts=list(DEFAULT_HOSTS),
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
    return cert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Initialize the first Light-Keeper HASEOS cert on this machine (HITL)."
        )
    )
    parser.add_argument(
        "--sovereign-id",
        required=True,
        help="Your Light-Keeper sovereign id (HITL-chosen)",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"Cert JSON path (default {DEFAULT_OUT}; gitignored via dsm_cert*.json)",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=DEFAULT_HOURS,
        help=f"Hours until expiry (default {DEFAULT_HOURS})",
    )
    parser.add_argument("--issuer", default=DEFAULT_ISSUER)
    parser.add_argument(
        "--tool",
        action="append",
        dest="tools",
        default=None,
        help="slice_tools entry (repeatable; default: status only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cert = init_light_keeper_cert(
            sovereign_id=args.sovereign_id,
            out_path=args.out,
            hours=args.hours,
            issuer=args.issuer,
            tools=args.tools,
        )
    except InitError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    # Print cert JSON only — never the secret.
    sys.stdout.write(json.dumps(cert, sort_keys=True, indent=2) + "\n")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
