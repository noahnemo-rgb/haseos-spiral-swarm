#!/usr/bin/env python3
"""D18 — Senior cert placement beside USB-state (HITL promotion).

QueenBee may propose sovereign_id / slice fields. Light-Keeper signs.
No Keeper secret on the USB image. Witness sibling stays ``<image>.dsm_witness.jsonl``.
Turn-off is revoke/park/freeze — essence, Witness, and USB-state remain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from haos_dsm_cert import cert_id_of
from haos_dsm_usb import export_witness_beside_usb

SENIOR_CERT_FILENAME = "dsm_cert_senior.json"


def _host_set(cert: dict | None) -> set[str] | None:
    if not isinstance(cert, dict):
        return None
    raw = cert.get("slice_hosts")
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return None
    return {str(h).strip().lower() for h in raw if str(h).strip()}


def _tool_set(cert: dict | None) -> set[str] | None:
    if not isinstance(cert, dict):
        return None
    raw = cert.get("slice_tools")
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return None
    return {str(t).strip() for t in raw if str(t).strip()}


def senior_slice_fits_queenbee(senior_cert: dict, queenbee_cert: dict) -> bool:
    """True iff senior WorldSlice ⊆ QueenBee WorldSlice.

    Hosts compared strip/lower. Tools compared as exact names.
    Missing or empty senior lists fail closed (not allow-all).
    """
    senior_hosts = _host_set(senior_cert)
    queen_hosts = _host_set(queenbee_cert)
    senior_tools = _tool_set(senior_cert)
    queen_tools = _tool_set(queenbee_cert)
    if senior_hosts is None or senior_tools is None:
        return False
    if not senior_hosts or not senior_tools:
        return False
    if queen_hosts is None or queen_tools is None:
        return False
    return senior_hosts <= queen_hosts and senior_tools <= queen_tools


def place_senior_cert_beside_usb(
    usb_image_path: str | Path,
    cert: dict,
    *,
    primary_witness: str | Path | None = None,
) -> Path:
    """Write ``dsm_cert_senior.json`` beside a USB-state image.

    Notes record cert_id / role / sovereign_id / path only — never the secret.
    Witness sibling remains ``<image>.dsm_witness.jsonl``.
    """
    image = Path(usb_image_path)
    dest = image.parent / SENIOR_CERT_FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(cert, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    state: dict[str, Any] | None = None
    if image.is_file():
        import usb_state

        state = usb_state.load(image)
        notes = state.get("notes")
        if not isinstance(notes, dict):
            notes = {}
            state["notes"] = notes
        notes["dsm_cert_senior"] = {
            "cert_id": cert_id_of(cert),
            "role": str(cert.get("role") or "senior"),
            "sovereign_id": str(cert.get("sovereign_id") or ""),
            "path": str(dest),
        }
        if primary_witness is not None:
            from haos_dsm import WitnessLog

            WitnessLog(primary_witness).append(
                {
                    "kind": "senior_cert_placed",
                    "reason": "allowed",
                    "lineage_id": str(cert.get("sovereign_id") or ""),
                    "detail": {
                        "cert_id": cert_id_of(cert),
                        "role": "senior",
                        "usb_image": str(image),
                    },
                }
            )
        usb_state.save(state, image)
        export_witness_beside_usb(
            image,
            primary_witness=primary_witness,
            state=state,
        )
        if isinstance(state.get("notes"), dict):
            usb_state.touch(state)
            image.write_text(
                json.dumps(state, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    return dest
