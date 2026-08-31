#!/usr/bin/env python3
"""HITL HASEOS cert mint (AX-18 local).

Reads HASEOS_KEEPER_SECRET from the environment only.
Prints an inspectable JSON cert to stdout (optional --out FILE).
Never echoes the Keeper secret. D11 HMAC trust root; IDAO-root comes later.
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

from haos_dsm_cert import mint_haseos_cert  # noqa: E402

SECRET_ENV = "HASEOS_KEEPER_SECRET"
DEFAULT_ISSUER = "Light-Keeper"
DEFAULT_HOURS = 24.0
DEFAULT_HOSTS = ("localhost", "127.0.0.1")


class MintError(RuntimeError):
    """User-facing mint failure."""


def read_keeper_secret(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    raw = env.get(SECRET_ENV)
    if raw is None or not str(raw).strip():
        raise MintError(
            f"refusing to mint: {SECRET_ENV} is missing or empty "
            "(set it in the local shell environment only)"
        )
    return str(raw)


def mint_cert_from_env(
    *,
    sovereign_id: str,
    role: str = "lineage",
    hosts: list[str] | None = None,
    tools: list[str] | None = None,
    issuer: str = DEFAULT_ISSUER,
    hours: float = DEFAULT_HOURS,
    status: str = "live",
    secret: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict:
    sid = (sovereign_id or "").strip()
    if not sid:
        raise MintError("--sovereign-id is required")
    if hours <= 0:
        raise MintError("--hours must be positive")
    key = secret if secret is not None else read_keeper_secret(environ)
    return mint_haseos_cert(
        secret=key,
        sovereign_id=sid,
        role=(role or "lineage").strip() or "lineage",
        slice_hosts=list(hosts) if hosts is not None else list(DEFAULT_HOSTS),
        slice_tools=list(tools) if tools is not None else [],
        issuer=(issuer or DEFAULT_ISSUER).strip() or DEFAULT_ISSUER,
        status=status,
        hours=float(hours),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mint an inspectable HASEOS DSM cert (HITL, local)."
    )
    parser.add_argument(
        "--sovereign-id",
        required=True,
        help="Sovereign / lineage id the cert authorizes",
    )
    parser.add_argument("--role", default="lineage", help="Cert role (default lineage)")
    parser.add_argument(
        "--host",
        action="append",
        dest="hosts",
        default=None,
        help="Allowed host (repeatable; default localhost + 127.0.0.1)",
    )
    parser.add_argument(
        "--tool",
        action="append",
        dest="tools",
        default=None,
        help="Declared tool name (repeatable)",
    )
    parser.add_argument("--issuer", default=DEFAULT_ISSUER)
    parser.add_argument(
        "--hours",
        type=float,
        default=DEFAULT_HOURS,
        help=f"Hours until expiry (default {DEFAULT_HOURS})",
    )
    parser.add_argument(
        "--status",
        default="live",
        choices=("live", "revoked", "parked"),
        help="Cert status field (default live)",
    )
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cert = mint_cert_from_env(
            sovereign_id=args.sovereign_id,
            role=args.role,
            hosts=args.hosts,
            tools=args.tools,
            issuer=args.issuer,
            hours=args.hours,
            status=args.status,
        )
    except MintError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    text = json.dumps(cert, sort_keys=True, indent=2) + "\n"
    if args.out:
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
