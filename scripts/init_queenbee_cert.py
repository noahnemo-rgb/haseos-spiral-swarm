#!/usr/bin/env python3
"""QueenBee cert — minted by Light-Keeper on the AX-18 (HITL).

Secret from HASEOS_KEEPER_SECRET env only. Never writes the secret.
QueenBee receives the cert JSON file later — not the Keeper secret.
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

SECRET_ENV = "HASEOS_KEEPER_SECRET"
DEFAULT_OUT = "dsm_cert_queenbee.json"
DEFAULT_SOVEREIGN = "queenbee.orchestrator"
DEFAULT_ISSUER = "Light-Keeper"
DEFAULT_ROLE = "queenbee"
DEFAULT_HOSTS = ("localhost", "127.0.0.1")
DEFAULT_FALLBACK_TOOLS = ("status", "wading_pool.select")
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


def resolve_queenbee_slice_tools(
    registry_path: str | Path | None = None,
) -> list[str]:
    """Prefer harness registry allow-list; else status + wading_pool.select."""
    try:
        import haos_dsm_hook

        names = haos_dsm_hook.declared_tools_from_registry(registry_path)
        if names:
            return sorted(names)
    except Exception:
        pass
    return list(DEFAULT_FALLBACK_TOOLS)


def init_queenbee_cert(
    *,
    sovereign_id: str = DEFAULT_SOVEREIGN,
    out_path: str | Path = DEFAULT_OUT,
    hours: float = DEFAULT_HOURS,
    issuer: str = DEFAULT_ISSUER,
    tools: list[str] | None = None,
    registry_path: str | Path | None = None,
    secret: str | None = None,
    environ: dict[str, str] | None = None,
    write_file: bool = True,
) -> dict:
    """Mint a live queenbee cert. Never writes the Keeper secret."""
    sid = (sovereign_id or "").strip() or DEFAULT_SOVEREIGN
    if hours <= 0:
        raise InitError("--hours must be positive")
    key = secret if secret is not None else read_keeper_secret(environ)
    if tools is not None:
        slice_tools = list(tools)
    else:
        slice_tools = resolve_queenbee_slice_tools(registry_path)
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
        description="Mint the QueenBee HASEOS cert (Light-Keeper HITL, local)."
    )
    parser.add_argument(
        "--sovereign-id",
        default=DEFAULT_SOVEREIGN,
        help=f"QueenBee sovereign id (default {DEFAULT_SOVEREIGN})",
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
        "--tool",
        action="append",
        dest="tools",
        default=None,
        help="slice_tools entry (repeatable; default: registry allow-list)",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Optional harness_registry.json path for slice_tools",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cert = init_queenbee_cert(
            sovereign_id=args.sovereign_id,
            out_path=args.out,
            hours=args.hours,
            issuer=args.issuer,
            tools=args.tools,
            registry_path=args.registry,
        )
    except InitError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(cert, sort_keys=True, indent=2) + "\n")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
