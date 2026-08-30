#!/usr/bin/env python3
"""Dual NAS Infinity Brain — HITL local filesystem memory loops.

Stdlib only. Does not import QueenBee. Does not create configured node roots.
Packages are pure JSON (haseos.infinity_memory.v1).
Sparse by design: no automatic writes, no invented paths.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from inference_client import load_env_file

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / "infinity_brain.env"
SCHEMA = "haseos.infinity_memory.v1"
INDEX_SCHEMA = "haseos.infinity_index.v1"
INDEX_NAME = "index.json"
LOOPS_DIR = "loops"
WHAT_CHOICES = ("experiences", "academy", "promotion", "all")
NODE_KEYS = ("A", "B")

load_env_file(ENV_FILE)


def node_paths() -> dict[str, str]:
    """Configured paths. Empty string means not configured. No invented defaults."""
    return {
        "A": (os.environ.get("INFINITY_BRAIN_NODE_A") or "").strip(),
        "B": (os.environ.get("INFINITY_BRAIN_NODE_B") or "").strip(),
    }


def parse_node_spec(spec: str | None) -> list[str]:
    raw = (spec or "A").strip().upper()
    if raw in {"A", "B"}:
        return [raw]
    if raw in {"BOTH", "AB", "A,B"}:
        return ["A", "B"]
    raise ValueError("Node must be A, B, or both")


def readiness_label(info: dict) -> str:
    """One calm readiness word for a node inspect dict."""
    if not info.get("configured"):
        return "idle"
    if not info.get("exists"):
        return "waiting"
    if not info.get("writable"):
        return "blocked"
    return "ready"


def readiness_hint(info: dict) -> str:
    key = info.get("key") or "?"
    if not info.get("configured"):
        return f"set INFINITY_BRAIN_NODE_{key} in infinity_brain.env when the mount exists"
    if not info.get("exists"):
        return "path missing — create or mount it before /memory loop"
    if not info.get("writable"):
        return "path not writable — fix permissions, then retry"
    return "HITL /memory loop may write here"


def package_content_bits(package: dict | None) -> dict:
    """Compact content flags from a package dict. Schema unchanged."""
    package = package or {}
    experiences = package.get("experiences") or {}
    if isinstance(experiences, dict):
        exp_count = experiences.get("count")
        if exp_count is None:
            exp_count = len(experiences.get("experiences") or [])
    elif isinstance(experiences, list):
        exp_count = len(experiences)
    else:
        exp_count = 0
    academy = package.get("academy")
    promotion = package.get("promotion") or {}
    return {
        "experiences": int(exp_count or 0) if "experiences" in package else None,
        "academy": bool(academy) if "academy" in package else False,
        "promotion": bool(promotion) if "promotion" in package else False,
        "promotion_history": len(promotion.get("history") or []) if isinstance(promotion, dict) else 0,
    }


def format_content_bits(bits: dict | None) -> str:
    bits = bits or {}
    parts = []
    if bits.get("experiences") is not None:
        parts.append(f"exp={bits['experiences']}")
    if bits.get("academy"):
        parts.append("academy")
    if bits.get("promotion"):
        hist = bits.get("promotion_history") or 0
        parts.append(f"promo={hist}" if hist else "promo")
    return " ".join(parts) if parts else "-"


def _package_timestamps(rows: list[dict]) -> tuple[str, str]:
    stamps = []
    for row in rows or []:
        stamp = (row.get("packaged_at") or "").strip()
        if stamp:
            stamps.append(stamp)
    if not stamps:
        return "", ""
    stamps.sort()
    return stamps[0], stamps[-1]


def inspect_node(key: str) -> dict:
    key = key.upper()
    path = node_paths().get(key, "")
    info = {
        "key": key,
        "path": path or "",
        "configured": bool(path),
        "exists": False,
        "writable": False,
        "error": "",
        "packages": 0,
        "bytes": 0,
        "oldest": "",
        "newest": "",
        "readiness": "idle",
        "hint": "",
    }
    if not path:
        info["error"] = f"INFINITY_BRAIN_NODE_{key} is not configured"
        info["readiness"] = readiness_label(info)
        info["hint"] = readiness_hint(info)
        return info
    root = Path(path)
    if not root.exists():
        info["error"] = f"configured path does not exist: {path}"
        info["readiness"] = readiness_label(info)
        info["hint"] = readiness_hint(info)
        return info
    if not root.is_dir():
        info["error"] = f"configured path is not a directory: {path}"
        info["readiness"] = readiness_label(info)
        info["hint"] = readiness_hint(info)
        return info
    info["exists"] = True
    info["writable"] = os.access(root, os.W_OK)
    if not info["writable"]:
        info["error"] = f"configured path is not writable: {path}"
    rows = list_packages(key, ignore_errors=True)
    info["packages"] = len(rows)
    info["oldest"], info["newest"] = _package_timestamps(rows)
    total_bytes = 0
    for row in rows:
        try:
            total_bytes += int(row.get("bytes") or 0)
        except (TypeError, ValueError):
            pass
        if not row.get("bytes"):
            rel = row.get("file") or ""
            candidate = root / rel
            if candidate.is_file():
                try:
                    total_bytes += candidate.stat().st_size
                except OSError:
                    pass
    info["bytes"] = total_bytes
    info["readiness"] = readiness_label(info)
    info["hint"] = readiness_hint(info)
    return info


def config_overview() -> dict:
    """Sparse dual-node readiness overview for /memory config."""
    nodes = {key: inspect_node(key) for key in NODE_KEYS}
    ready = sum(1 for info in nodes.values() if info.get("readiness") == "ready")
    packages = sum(int(info.get("packages") or 0) for info in nodes.values())
    return {
        "schema": SCHEMA,
        "index_schema": INDEX_SCHEMA,
        "env_file": str(ENV_FILE),
        "default_loop_node": "A",
        "auto_loop": False,
        "nodes_ready": ready,
        "nodes_total": len(NODE_KEYS),
        "packages_total": packages,
        "nodes": nodes,
        "summary": (
            f"{ready}/{len(NODE_KEYS)} nodes ready · "
            f"{packages} package(s) · HITL only · default node A"
        ),
    }


def require_writable_node(key: str) -> Path:
    info = inspect_node(key)
    if info["error"]:
        raise FileNotFoundError(info["error"]) if not info["exists"] else PermissionError(info["error"])
    return Path(info["path"])


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (value or "unknown"))
    return cleaned[:80] or "unknown"


def _index_path(root: Path) -> Path:
    return root / INDEX_NAME


def _read_index(root: Path) -> dict:
    path = _index_path(root)
    if not path.exists():
        return {"schema": INDEX_SCHEMA, "packages": []}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return {"schema": INDEX_SCHEMA, "packages": []}
        data.setdefault("schema", INDEX_SCHEMA)
        data.setdefault("packages", [])
        if not isinstance(data["packages"], list):
            data["packages"] = []
        return data
    except (OSError, json.JSONDecodeError):
        return {"schema": INDEX_SCHEMA, "packages": []}


def _write_index(root: Path, index: dict) -> None:
    path = _index_path(root)
    path.write_text(json.dumps(index, indent=2) + "\n")


def write_package(key: str, package: dict) -> dict:
    """Write one JSON package under an existing node root. Creates loops/<id>/ only."""
    root = require_writable_node(key)
    infant_id = _safe_name((package.get("source") or {}).get("infant_id") or "unknown")
    what = _safe_name((package.get("source") or {}).get("what") or "all")
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    folder = root / LOOPS_DIR / infant_id
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{infant_id}_{stamp}_{what}_node{key}.json"
    dest = folder / filename
    dest.write_text(json.dumps(package, indent=2) + "\n")
    rel = str(dest.relative_to(root))
    bits = package_content_bits(package)
    size = dest.stat().st_size
    entry = {
        "file": rel,
        "infant_id": (package.get("source") or {}).get("infant_id"),
        "packaged_at": package.get("packaged_at"),
        "what": (package.get("source") or {}).get("what"),
        "schema": package.get("schema"),
        "node": key,
        "bytes": size,
        "contents": bits,
    }
    index = _read_index(root)
    index["node"] = key
    index["path"] = str(root)
    index["updated_at"] = datetime.now().isoformat()
    index["packages"].append(entry)
    _write_index(root, index)
    return {
        "node": key,
        "path": str(dest),
        "relative": rel,
        "bytes": size,
        "contents": bits,
        "schema": package.get("schema") or SCHEMA,
    }


def list_packages(key: str, ignore_errors: bool = False) -> list[dict]:
    path = node_paths().get(key.upper(), "")
    if not path:
        if ignore_errors:
            return []
        raise FileNotFoundError(f"INFINITY_BRAIN_NODE_{key.upper()} is not configured")
    root = Path(path)
    if not root.is_dir():
        if ignore_errors:
            return []
        raise FileNotFoundError(f"configured path does not exist: {path}")
    index = _read_index(root)
    packages = list(index.get("packages") or [])
    if packages:
        return packages
    loops = root / LOOPS_DIR
    if not loops.is_dir():
        return []
    found = []
    for file in sorted(loops.rglob("*.json")):
        try:
            size = file.stat().st_size
        except OSError:
            size = 0
        found.append(
            {
                "file": str(file.relative_to(root)),
                "infant_id": file.parent.name,
                "packaged_at": "",
                "what": "",
                "schema": "",
                "node": key.upper(),
                "bytes": size,
                "contents": {},
            }
        )
    return found


def read_package(key: str, relative_or_name: str) -> dict:
    info = inspect_node(key)
    if info["error"] and not info["exists"]:
        raise FileNotFoundError(info["error"])
    root = Path(info["path"])
    hint = (relative_or_name or "").strip()
    candidates = []
    direct = root / hint
    if direct.is_file():
        candidates.append(direct)
    for pkg in list_packages(key, ignore_errors=True):
        rel = pkg.get("file") or ""
        if rel == hint or Path(rel).name == hint or hint in rel:
            candidates.append(root / rel)
    if not candidates:
        raise FileNotFoundError(f"package not found on node {key}: {hint}")
    path = candidates[-1]
    data = json.loads(path.read_text())
    return {
        "path": str(path),
        "package": data,
        "bytes": path.stat().st_size,
        "contents": package_content_bits(data),
    }
