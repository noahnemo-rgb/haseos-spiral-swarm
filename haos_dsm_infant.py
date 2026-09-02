#!/usr/bin/env python3
"""D19 — Infant cert placement beside USB-state (HITL promotion).

Light-Keeper signs. Infant WorldSlice ⊆ Senior WorldSlice
(and ⊆ QueenBee when that cert is supplied).
No Keeper secret on the USB image. Witness sibling stays ``<image>.dsm_witness.jsonl``.
Turn-off is revoke/park/freeze — essence, Witness, and USB-state remain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from haos_dsm_cert import cert_id_of
from haos_dsm_senior import senior_slice_fits_queenbee
from haos_dsm_usb import export_witness_beside_usb

INFANT_CERT_FILENAME = "dsm_cert_infant.json"


def infant_slice_fits_senior(infant_cert: dict, senior_cert: dict) -> bool:
    """True iff infant WorldSlice ⊆ Senior WorldSlice (same set math as D18)."""
    return senior_slice_fits_queenbee(infant_cert, senior_cert)


def infant_slice_fits_chain(
    infant_cert: dict,
    senior_cert: dict,
    queenbee_cert: dict | None = None,
) -> bool:
    """infant ⊆ senior and (queenbee is None or infant ⊆ queenbee)."""
    if not infant_slice_fits_senior(infant_cert, senior_cert):
        return False
    if queenbee_cert is None:
        return True
    return senior_slice_fits_queenbee(infant_cert, queenbee_cert)


def place_infant_cert_beside_usb(
    usb_image_path: str | Path,
    cert: dict,
    *,
    primary_witness: str | Path | None = None,
) -> Path:
    """Write ``dsm_cert_infant.json`` beside a USB-state image.

    Notes record cert_id / role / sovereign_id / path only — never the secret.
    Witness sibling remains ``<image>.dsm_witness.jsonl``.
    """
    image = Path(usb_image_path)
    dest = image.parent / INFANT_CERT_FILENAME
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
        notes["dsm_cert_infant"] = {
            "cert_id": cert_id_of(cert),
            "role": str(cert.get("role") or "infant"),
            "sovereign_id": str(cert.get("sovereign_id") or ""),
            "path": str(dest),
        }
        if primary_witness is not None:
            from haos_dsm import WitnessLog

            WitnessLog(primary_witness).append(
                {
                    "kind": "infant_cert_placed",
                    "reason": "allowed",
                    "lineage_id": str(cert.get("sovereign_id") or ""),
                    "detail": {
                        "cert_id": cert_id_of(cert),
                        "role": "infant",
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
