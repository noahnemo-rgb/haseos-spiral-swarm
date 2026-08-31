#!/usr/bin/env python3
"""DSM D5 — Witness copy beside a USB-state image (software twin only).

Append-only hash-chained JSONL sibling. No Keeper secret on the image.
No physical USB / GPIO / serial. Stdlib only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from haos_dsm import WITNESS_SCHEMA, WitnessLog, verify_witness_chain

GENESIS = "0" * 64
SIBLING_SUFFIX = ".dsm_witness.jsonl"

# Re-export for callers/tests.
__all__ = [
    "SIBLING_SUFFIX",
    "annotate_and_export_witness",
    "export_witness_beside_usb",
    "sibling_witness_path",
    "sync_witness_copy",
    "usb_witness_log",
    "verify_witness_chain",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_primary_witness() -> Path:
    try:
        from haos_dsm_hook import DEFAULT_WITNESS

        return Path(DEFAULT_WITNESS)
    except ImportError:
        return Path(__file__).resolve().parent / "dsm_witness.jsonl"


def sibling_witness_path(usb_image_path: str | Path) -> Path:
    """Witness lives beside the USB-state JSON: ``<image>.dsm_witness.jsonl``."""
    return Path(str(usb_image_path) + SIBLING_SUFFIX)


def _read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("hash"):
            rows.append(row)
    return rows


def sync_witness_copy(
    primary_witness: str | Path,
    usb_witness_copy: str | Path,
) -> dict:
    """Append primary Witness events onto the USB copy without breaking the chain.

    Lines are copied verbatim (same hashes). Lineage cannot truncate the copy.
    """
    primary = Path(primary_witness)
    dest = Path(usb_witness_copy)
    if not primary.is_file():
        return {"status": "skipped", "reason": "no_primary_witness", "path": str(primary)}
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text("", encoding="utf-8")

    primary_rows = _read_rows(primary)
    dest_rows = _read_rows(dest)
    dest_hashes = {str(r.get("hash")) for r in dest_rows}
    tip = str(dest_rows[-1]["hash"]) if dest_rows else GENESIS
    added = 0
    with dest.open("a", encoding="utf-8") as out:
        for row in primary_rows:
            h = str(row.get("hash") or "")
            if not h or h in dest_hashes:
                continue
            if str(row.get("prev_hash")) != tip:
                continue
            out.write(json.dumps(row, sort_keys=True) + "\n")
            tip = h
            dest_hashes.add(h)
            added += 1
    return {
        "status": "exported",
        "added": added,
        "path": str(dest),
        "tip": tip,
        "primary": str(primary),
    }


def export_witness_beside_usb(
    usb_image_path: str | Path,
    *,
    primary_witness: str | Path | None = None,
    state: dict | None = None,
) -> dict:
    """Export Witness beside a USB-state image. Skip calmly if image/witness absent."""
    image = Path(usb_image_path) if usb_image_path else None
    if image is None or not image.is_file():
        return {"status": "skipped", "reason": "no_usb_image"}
    primary = Path(primary_witness) if primary_witness else _default_primary_witness()
    if not primary.is_file() or not _read_rows(primary):
        return {
            "status": "skipped",
            "reason": "no_primary_witness",
            "primary": str(primary),
        }
    dest = sibling_witness_path(image)
    result = sync_witness_copy(primary, dest)
    result["usb_image"] = str(image)
    result["relative"] = dest.name
    if state is not None and isinstance(state, dict) and result.get("status") == "exported":
        notes = state.get("notes")
        if not isinstance(notes, dict):
            notes = {}
            state["notes"] = notes
        notes["dsm_witness_copy"] = {
            "schema": WITNESS_SCHEMA,
            "file": dest.name,
            "path": str(dest),
            "tip_hash": result.get("tip"),
            "exported_at": _utc_now(),
            "note": "Append-only Witness sibling beside USB-state. No Keeper secret.",
        }
    return result


def usb_witness_log(usb_image_path: str | Path) -> WitnessLog:
    """Open the USB Witness copy as an append-only WitnessLog (truncate forbidden)."""
    return WitnessLog(sibling_witness_path(usb_image_path))


def annotate_and_export_witness(
    state: dict,
    usb_image_path: str | Path,
    *,
    primary_witness: str | Path | None = None,
) -> dict:
    """Hook target for usb_state.save — export sibling + document in state notes."""
    return export_witness_beside_usb(
        usb_image_path,
        primary_witness=primary_witness,
        state=state,
    )
