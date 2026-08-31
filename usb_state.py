#!/usr/bin/env python3
"""
USB-state image — canonical, human-readable node snapshot.

This is the software stand-in for a physical USB drive that will later
move infant state on and off real Android phones (air-gapped).

Standard library only. Inspectable JSON. Memory Sovereignty.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "0.2"
INFANT_SNAPSHOT_SCHEMA = "haseos.usb_infant.v1"
MOUNT_STATUSES = {"mounted", "ejected", "offline"}
MODES = {"memory", "file"}

REQUIRED_KEYS = (
    "schema_version",
    "node_id",
    "created_at",
    "last_sync",
    "last_modified",
    "mount_status",
    "airgap_enforced",
    "mode",
    "path",
    "infants",
    "offline_queue",
    "competence_scores",
    "experience_logs",
    "academy_status",
    "memory_manifest",
    "capacity",
    "notes",
    "integrity",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_payload(state: dict) -> dict:
    """Deep copy of state without the integrity field (used for hashing)."""
    payload = copy.deepcopy(state)
    payload.pop("integrity", None)
    return payload


def compute_integrity(state: dict) -> str:
    """SHA-256 of canonical JSON, excluding the integrity field itself."""
    blob = json.dumps(
        _canonical_payload(state),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def create_empty(
    node_id: str,
    mode: str = "memory",
    path: str | None = None,
    max_infants: int = 4,
    storage_mb: int = 1024,
    hardware_profile: str = "sim-virtual",
) -> dict:
    """Return a fresh USB-state dict. Integrity is filled by touch()."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}, got {mode!r}")
    stamp = _now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "node_id": str(node_id),
        "created_at": stamp,
        "last_sync": stamp,
        "last_modified": stamp,
        "mount_status": "offline",
        "airgap_enforced": True,
        "mode": mode,
        "path": str(path) if path else None,
        "infants": [],
        "offline_queue": [],
        "competence_scores": {},
        "experience_logs": {},
        "academy_status": {},
        "memory_manifest": {},
        "capacity": {
            "max_infants": int(max_infants),
            "storage_mb": int(storage_mb),
        },
        "notes": {
            "hardware_profile": hardware_profile,
        },
        "integrity": "",
    }
    return touch(state)


def from_dict(data: dict) -> dict:
    """Normalize / soft-upgrade an incoming dict to the current schema."""
    if not isinstance(data, dict):
        raise TypeError("USB-state data must be a dict")
    base = create_empty(
        node_id=str(data.get("node_id") or "unnamed-node"),
        mode=data.get("mode") if data.get("mode") in MODES else "memory",
        path=data.get("path"),
    )
    merged = copy.deepcopy(base)
    for key in REQUIRED_KEYS:
        if key in data and data[key] is not None:
            merged[key] = copy.deepcopy(data[key])
    # Soft-upgrade nested containers so older images still load.
    if not isinstance(merged.get("infants"), list):
        merged["infants"] = []
    if not isinstance(merged.get("offline_queue"), list):
        merged["offline_queue"] = []
    for map_key in (
        "competence_scores",
        "experience_logs",
        "academy_status",
        "memory_manifest",
        "notes",
    ):
        if not isinstance(merged.get(map_key), dict):
            merged[map_key] = {}
    cap = merged.get("capacity")
    if not isinstance(cap, dict):
        cap = {}
    merged["capacity"] = {
        "max_infants": int(cap.get("max_infants", 4)),
        "storage_mb": int(cap.get("storage_mb", 1024)),
    }
    if merged.get("mode") not in MODES:
        merged["mode"] = "memory"
    if merged.get("mount_status") not in MOUNT_STATUSES:
        merged["mount_status"] = "offline"
    merged["airgap_enforced"] = bool(merged.get("airgap_enforced", True))
    incoming_schema = data.get("schema_version")
    upgraded = incoming_schema != SCHEMA_VERSION or "memory_manifest" not in data
    merged["schema_version"] = SCHEMA_VERSION
    if not merged.get("integrity") or upgraded:
        merged["integrity"] = compute_integrity(merged)
    return merged


def to_dict(state: dict) -> dict:
    """Clean deep copy suitable for inspect or serialize."""
    return copy.deepcopy(state)


def infant_memory_card(infant: dict) -> dict:
    """Lightweight inspect card for richer memory on a stored infant. No invented history."""
    if not isinstance(infant, dict):
        return {
            "id": "?",
            "snapshot_schema": "",
            "experiences": 0,
            "has_academy_review": False,
            "academy_recommendation": "",
            "promoted": False,
            "promotion_events": 0,
            "competence": None,
            "status": "?",
            "sleeping": False,
        }
    experiences = infant.get("experiences")
    if not isinstance(experiences, list):
        experiences = []
    history = infant.get("promotion_history")
    if not isinstance(history, list):
        history = []
    review = infant.get("last_academy_review")
    if not isinstance(review, dict):
        review = {}
    return {
        "id": infant.get("id"),
        "snapshot_schema": infant.get("usb_snapshot_schema") or infant.get("experience_schema") or "",
        "experiences": len(experiences),
        "has_academy_review": bool(review),
        "academy_recommendation": review.get("recommendation") or "",
        "promoted": bool(infant.get("promoted")),
        "promotion_events": len(history),
        "competence": infant.get("competence_score"),
        "status": infant.get("status") or "?",
        "sleeping": infant.get("status") == "SLEEPING",
    }


def validate(state: dict) -> list[str]:
    """Return a list of problems. Empty list means the image is OK."""
    problems: list[str] = []
    if not isinstance(state, dict):
        return ["state is not a dict"]
    for key in REQUIRED_KEYS:
        if key not in state:
            problems.append(f"missing field: {key}")
    if state.get("mode") not in MODES:
        problems.append(f"invalid mode: {state.get('mode')!r}")
    if state.get("mount_status") not in MOUNT_STATUSES:
        problems.append(f"invalid mount_status: {state.get('mount_status')!r}")
    if not isinstance(state.get("airgap_enforced"), bool):
        problems.append("airgap_enforced must be a bool")
    if not isinstance(state.get("infants"), list):
        problems.append("infants must be a list")
    if not isinstance(state.get("offline_queue"), list):
        problems.append("offline_queue must be a list")
    for map_key in (
        "competence_scores",
        "experience_logs",
        "academy_status",
        "memory_manifest",
        "notes",
    ):
        if map_key in state and not isinstance(state.get(map_key), dict):
            problems.append(f"{map_key} must be a dict")
    cap = state.get("capacity")
    if not isinstance(cap, dict):
        problems.append("capacity must be a dict")
    else:
        if "max_infants" not in cap:
            problems.append("capacity.max_infants missing")
        if "storage_mb" not in cap:
            problems.append("capacity.storage_mb missing")
    if not state.get("node_id"):
        problems.append("node_id is empty")
    expected = compute_integrity(state)
    actual = state.get("integrity")
    if actual and actual != expected:
        problems.append("integrity mismatch (image may have been edited)")
    return problems


def touch(state: dict) -> dict:
    """Update last_modified and recompute integrity. Returns the same dict."""
    state["last_modified"] = _now()
    state["integrity"] = compute_integrity(state)
    return state


def save(state: dict, path: str | Path) -> dict:
    """Write pretty JSON. Updates path, last_sync, last_modified, integrity."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    state["path"] = str(dest)
    state["last_sync"] = _now()
    touch(state)
    problems = validate(state)
    if problems:
        raise ValueError("cannot save invalid USB-state: " + "; ".join(problems))
    dest.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # DSM D5 — Witness copy beside the image (skip if no primary Witness yet).
    try:
        from haos_dsm_usb import annotate_and_export_witness

        export_info = annotate_and_export_witness(state, dest)
        if export_info.get("status") == "exported" and isinstance(state.get("notes"), dict):
            touch(state)
            dest.write_text(
                json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    except ImportError:
        pass
    return state


def load(path: str | Path) -> dict:
    """Load + validate a JSON USB-state image."""
    dest = Path(path)
    raw = json.loads(dest.read_text(encoding="utf-8"))
    state = from_dict(raw)
    state["path"] = str(dest)
    problems = validate(state)
    if problems:
        raise ValueError(f"invalid USB-state {dest}: " + "; ".join(problems))
    return state


def _self_test() -> None:
    """Create, save, load, and verify integrity. Used by `python3 usb_state.py`."""
    import tempfile

    print("usb_state self-test starting")
    state = create_empty("self-test-node", mode="file")
    problems = validate(state)
    assert not problems, problems
    digest = state["integrity"]
    assert digest == compute_integrity(state)
    print(f"  created node_id={state['node_id']} integrity={digest[:12]}...")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "self-test-node.json"
        save(state, path)
        print(f"  saved {path}")
        loaded = load(path)
        print(f"  loaded mount_status={loaded['mount_status']} mode={loaded['mode']}")
        assert loaded["integrity"] == compute_integrity(loaded)
        assert loaded["node_id"] == "self-test-node"
        print("  integrity verified after save/load")

    print("usb_state self-test OK")


if __name__ == "__main__":
    _self_test()
