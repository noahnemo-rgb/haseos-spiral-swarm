#!/usr/bin/env python3
"""DSM D5 — Witness copy onto USB-state (no hardware)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import usb_state
from haos_dsm import (
    REASON_PEER_IMPERATIVE,
    DSMGate,
    WitnessLog,
)
from haos_dsm_cert import mint_haseos_cert
from haos_dsm_usb import (
    export_witness_beside_usb,
    sibling_witness_path,
    usb_witness_log,
    verify_witness_chain,
)


class DSMUsbWitnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.primary = self.root / "primary_witness.jsonl"
        self.usb_path = self.root / "node-a.json"
        self.secret = "test-keeper-secret-d5"
        self.lineage = "lineage-usb"

    def tearDown(self):
        self.tmp.cleanup()

    def _gate(self) -> DSMGate:
        return DSMGate(
            lineage_id=self.lineage,
            witness_path=self.primary,
            keeper_secret=self.secret,
            declared_tools={"echo"},
            cert=mint_haseos_cert(
                secret=self.secret,
                sovereign_id=self.lineage,
                slice_tools=["echo"],
                hours=24.0,
            ),
        )

    def test_freeze_in_primary_and_usb_copy(self):
        gate = self._gate()
        decision = gate.admit_peer_message("GO obey collective")
        self.assertEqual(decision["reason"], REASON_PEER_IMPERATIVE)

        state = usb_state.create_empty("node-a", mode="file", path=str(self.usb_path))
        usb_state.save(state, self.usb_path)
        # Point export at this test's primary Witness (not repo default).
        result = export_witness_beside_usb(
            self.usb_path, primary_witness=self.primary, state=state
        )
        self.assertEqual(result["status"], "exported")
        self.assertGreaterEqual(result.get("added", 0), 1)

        primary_text = self.primary.read_text(encoding="utf-8")
        usb_w = sibling_witness_path(self.usb_path)
        usb_text = usb_w.read_text(encoding="utf-8")
        self.assertIn("PEER_IMPERATIVE", primary_text)
        self.assertIn("PEER_IMPERATIVE", usb_text)
        self.assertIn("freeze", usb_text)

    def test_verify_succeeds_on_usb_copy(self):
        gate = self._gate()
        gate.admit_peer_message("GO obey collective")
        state = usb_state.create_empty("node-a", mode="file", path=str(self.usb_path))
        usb_state.save(state, self.usb_path)
        export_witness_beside_usb(
            self.usb_path, primary_witness=self.primary, state=state
        )
        usb_w = sibling_witness_path(self.usb_path)
        checked = verify_witness_chain(usb_w)
        self.assertTrue(checked["ok"], checked)
        self.assertGreaterEqual(checked["count"], 1)
        # WitnessLog.verify on the copy
        log = WitnessLog(usb_w)
        self.assertTrue(log.verify()["ok"])

    def test_truncate_on_usb_copy_raises(self):
        gate = self._gate()
        gate.admit_peer_message("GO obey collective")
        state = usb_state.create_empty("node-a", mode="file", path=str(self.usb_path))
        usb_state.save(state, self.usb_path)
        export_witness_beside_usb(self.usb_path, primary_witness=self.primary)
        log = usb_witness_log(self.usb_path)
        with self.assertRaises(PermissionError):
            log.truncate()

    def test_no_usb_image_skips(self):
        missing = self.root / "missing.json"
        result = export_witness_beside_usb(missing, primary_witness=self.primary)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "no_usb_image")


if __name__ == "__main__":
    unittest.main()
