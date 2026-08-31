#!/usr/bin/env python3
"""HITL DSM delegation token mint (AX-18 local).

Reads HASEOS_KEEPER_SECRET from the environment only.
Prints a JSON token to stdout (optional --out FILE).
Never echoes the Keeper secret. Stdlib + haos_dsm only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `python3 scripts/mint_dsm_token.py` from repo root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from haos_dsm import mint_delegation_token  # noqa: E402

SECRET_ENV = "HASEOS_KEEPER_SECRET"
DEFAULT_ISSUER = "Light-Keeper"
DEFAULT_HOURS = 1


class MintError(RuntimeError):
    """User-facing mint failure (missing secret, bad args)."""


def read_keeper_secret(environ: dict[str, str] | None = None) -> str:
    """Return Keeper secret from env. Refuse empty/missing. Never print it."""
    env = environ if environ is not None else os.environ
    raw = env.get(SECRET_ENV)
    if raw is None or not str(raw).strip():
        raise MintError(
            f"refusing to mint: {SECRET_ENV} is missing or empty "
            "(set it in the local shell environment only)"
        )
    return str(raw)


def mint_token(
    *,
    lineage: str,
    task: str,
    issuer: str = DEFAULT_ISSUER,
    scope: str | None = None,
    hours: float = DEFAULT_HOURS,
    secret: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict:
    """Mint a delegation token. Secret from arg or HASEOS_KEEPER_SECRET."""
    lineage_s = (lineage or "").strip()
    task_s = (task or "").strip()
    if not lineage_s:
        raise MintError("--lineage is required")
    if not task_s:
        raise MintError("--task is required")
    if hours <= 0:
        raise MintError("--hours must be positive")
    key = secret if secret is not None else read_keeper_secret(environ)
    scope_s = (scope if scope is not None else task_s).strip() or task_s
    expires = datetime.now(timezone.utc) + timedelta(hours=float(hours))
    return mint_delegation_token(
        secret=key,
        issuer=(issuer or DEFAULT_ISSUER).strip() or DEFAULT_ISSUER,
        target_lineage=lineage_s,
        task=task_s,
        expires_at=expires,
        scope=scope_s,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mint a Light-Keeper DSM HMAC delegation token (HITL, local)."
    )
    parser.add_argument("--lineage", required=True, help="Target lineage_id")
    parser.add_argument(
        "--task",
        required=True,
        help="Token task (e.g. UNFREEZE, GO)",
    )
    parser.add_argument(
        "--issuer",
        default=DEFAULT_ISSUER,
        help=f"Issuer label (default {DEFAULT_ISSUER})",
    )
    parser.add_argument(
        "--scope",
        default=None,
        help="Comma-separated scope (default: matches --task)",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=DEFAULT_HOURS,
        help=f"Hours until expiry (default {DEFAULT_HOURS})",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write JSON token (also printed to stdout)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        token = mint_token(
            lineage=args.lineage,
            task=args.task,
            issuer=args.issuer,
            scope=args.scope,
            hours=args.hours,
        )
    except MintError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    text = json.dumps(token, sort_keys=True, indent=2) + "\n"
    if args.out:
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
