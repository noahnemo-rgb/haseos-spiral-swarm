#!/usr/bin/env python3
"""D23 — Git hook checks for secrets, vendored trees, and origin URL.

Seatbelt only. DSM remains the gate. Stdlib only.
Never import queenbee_integration or torch.
Never read living certs or .haseos_keeper — names only.
Never print secret contents.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import PurePosixPath
from urllib.parse import urlparse

ALLOWED_ORIGIN = "https://github.com/noahnemo-rgb/haseos-spiral-swarm.git"

FORBIDDEN_NAME_PATTERNS = (
    ".haseos_keeper",
    "dsm_cert*.json",
    "dsm_witness.jsonl",
    ".dsm_witness.jsonl",
    "dsm_freeze.json",
    "dsm_token.json",
    "dsm_revocation.json",
    "queenbee_memory.json",
)

FORBIDDEN_TREE_PREFIXES = ("hrm/", "autoresearch/")
FORBIDDEN_SEGMENTS = frozenset({"skitter", "gpio"})


def _normalize(name: str) -> str:
    text = str(name or "").replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def _parts(name: str) -> tuple[str, ...]:
    return tuple(p for p in PurePosixPath(name).parts if p not in (".", "/"))


def _name_blocked(name: str) -> bool:
    norm = _normalize(name)
    if not norm:
        return False
    base = PurePosixPath(norm).name
    for pat in FORBIDDEN_NAME_PATTERNS:
        if fnmatch.fnmatch(base, pat) or fnmatch.fnmatch(norm, pat):
            return True
    if base.endswith(".dsm_witness.jsonl") or norm.endswith(".dsm_witness.jsonl"):
        return True
    lowered = norm.lower()
    for prefix in FORBIDDEN_TREE_PREFIXES:
        if lowered == prefix[:-1] or lowered.startswith(prefix):
            return True
    parts = [p.lower() for p in _parts(norm)]
    if any(seg in FORBIDDEN_SEGMENTS for seg in parts):
        return True
    return False


def check_staged_paths(names: list[str] | tuple[str, ...] | None) -> list[str]:
    """Return staged names that must not be committed."""
    blocked: list[str] = []
    seen: set[str] = set()
    for raw in names or ():
        text = str(raw).strip()
        if not text or text in seen:
            continue
        if _name_blocked(text):
            blocked.append(text)
            seen.add(text)
    return blocked


def check_origin_url(url: str | None) -> bool:
    """True only for the exact HTTPS origin. Refuse userinfo / PAT / extra path."""
    raw = str(url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    if parsed.username or parsed.password:
        return False
    if "@" in (parsed.netloc or ""):
        return False
    if parsed.scheme == "ssh" or raw.startswith("git@"):
        return False
    if raw != ALLOWED_ORIGIN:
        return False
    if parsed.scheme != "https":
        return False
    if parsed.hostname != "github.com":
        return False
    if parsed.path != "/noahnemo-rgb/haseos-spiral-swarm.git":
        return False
    if parsed.query or parsed.fragment or parsed.params:
        return False
    return True


def _read_staged_names(argv_names: list[str]) -> list[str]:
    if argv_names:
        return list(argv_names)
    if not sys.stdin.isatty():
        return [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="D23 git hook checks (names and origin only; never prints secrets)."
    )
    parser.add_argument(
        "--check-staged",
        action="store_true",
        help="Refuse forbidden staged paths (stdin, args, or git diff --cached)",
    )
    parser.add_argument(
        "--check-origin",
        metavar="URL",
        default=None,
        help="Refuse unless URL is exactly ALLOWED_ORIGIN (no userinfo)",
    )
    parser.add_argument("names", nargs="*", help="Optional staged paths")
    args = parser.parse_args(argv)
    if not args.check_staged and args.check_origin is None:
        parser.error("need --check-staged and/or --check-origin")

    rc = 0
    if args.check_staged:
        blocked = check_staged_paths(_read_staged_names(args.names))
        if blocked:
            print(
                "D23 blocked staged path(s). Named git add only. "
                "--no-verify is HITL override.",
                file=sys.stderr,
            )
            for name in blocked:
                print(name, file=sys.stderr)
            rc = 1
    if args.check_origin is not None:
        if not check_origin_url(args.check_origin):
            print(
                "D23 blocked origin URL (not ALLOWED_ORIGIN; "
                "userinfo / PAT / extra path refused).",
                file=sys.stderr,
            )
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
