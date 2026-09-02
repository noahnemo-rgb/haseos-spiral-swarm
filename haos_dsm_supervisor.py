#!/usr/bin/env python3
"""D21 — Team Leading Supervisor/QC cert placement beside USB-state (HITL).

Light-Keeper signs. Supervisor WorldSlice ⊆ Chief of Staff WorldSlice
(and ⊆ Light-Keeper when that cert is supplied).
No Keeper secret on the USB image. Witness sibling stays ``<image>.dsm_witness.jsonl``.
Turn-off is revoke/park/freeze — essence, Witness, and USB-state remain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from haos_dsm_cert import cert_id_of
from haos_dsm_chief import chief_slice_fits_lightkeeper
from haos_dsm_usb import export_witness_beside_usb

SUPERVISOR_CERT_FILENAME = "dsm_cert_supervisor_qc.json"


def supervisor_slice_fits_chief(supervisor_cert: dict, chief_cert: dict) -> bool:
    """True iff Supervisor WorldSlice ⊆ Chief of Staff WorldSlice (same set math as D20)."""
    return chief_slice_fits_lightkeeper(supervisor_cert, chief_cert)


def place_supervisor_cert_beside_usb(
    usb_image_path: str | Path,
    cert: dict,
    *,
    primary_witness: str | Path | None = None,
) -> Path:
    """Write ``dsm_cert_supervisor_qc.json`` beside a USB-state image.

    Notes record cert_id / role / sovereign_id / path only — never the secret.
    Witness sibling remains ``<image>.dsm_witness.jsonl``.
    """
    image = Path(usb_image_path)
    dest = image.parent / SUPERVISOR_CERT_FILENAME
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
        notes["dsm_cert_supervisor_qc"] = {
            "cert_id": cert_id_of(cert),
            "role": str(cert.get("role") or "supervisor-qc"),
            "sovereign_id": str(cert.get("sovereign_id") or ""),
            "path": str(dest),
        }
        if primary_witness is not None:
            from haos_dsm import WitnessLog

            WitnessLog(primary_witness).append(
                {
                    "kind": "supervisor_cert_placed",
                    "reason": "allowed",
                    "lineage_id": str(cert.get("sovereign_id") or ""),
                    "detail": {
                        "cert_id": cert_id_of(cert),
                        "role": "supervisor-qc",
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
