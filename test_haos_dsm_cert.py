#!/usr/bin/env python3
"""DSM D11 tests — HASEOS cert trust path (turn-off, never destroy)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from haos_dsm import DSMGate, default_freeze_path
from haos_dsm_cert import (
    REASON_CERT_INVALID,
    REASON_CERT_REVOKED,
    cert_id_of,
    mint_haseos_cert,
    verify_cert,
)


class HaseosCertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.witness = Path(self.tmp.name) / "witness.jsonl"
        self.secret = "test-keeper-secret-d11"
        self.lineage = "lineage-cert-d11"

    def tearDown(self):
        self.tmp.cleanup()

    def _cert(self, **kwargs):
        base = dict(
            secret=self.secret,
            sovereign_id=self.lineage,
            role="lineage",
            slice_hosts=["localhost", "127.0.0.1"],
            slice_tools=["echo", "status"],
            hours=24.0,
        )
        base.update(kwargs)
        return mint_haseos_cert(**base)

    def _gate(self, cert=None, **kwargs):
        return DSMGate(
            lineage_id=self.lineage,
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"echo", "status"},
            cert=cert,
            **kwargs,
        )

    def test_live_matching_cert_observation_admitted(self):
        cert = self._cert()
        gate = self._gate(cert=cert)
        decision = gate.admit_peer_message("I observe the host is localhost")
        self.assertTrue(decision["allowed"])
        self.assertFalse(decision["frozen"])
        check = verify_cert(
            cert, secret=self.secret, expected_sovereign_id=self.lineage
        )
        self.assertTrue(check["ok"])

    def test_missing_cert_refused(self):
        gate = self._gate(cert=None)
        decision = gate.admit_peer_message("I observe the host is localhost")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_CERT_INVALID)
        tip = gate.witness.path.read_text(encoding="utf-8")
        self.assertIn("CERT_INVALID", tip)
        self.assertNotIn(self.secret, tip)

    def test_revoked_cert_refused_witness_and_freeze_persist(self):
        cert = self._cert()
        gate = self._gate(cert=cert)
        before_witness = self.witness.read_text(encoding="utf-8") if self.witness.exists() else ""
        turned_off = gate.revoke_authority()
        self.assertEqual(turned_off["reason"], REASON_CERT_REVOKED)
        self.assertTrue(gate.frozen)
        self.assertTrue(gate.revocation_path.is_file())
        self.assertTrue(default_freeze_path(self.witness).is_file())
        # Essence / Witness remain — no deletion.
        self.assertTrue(self.witness.is_file())
        after = self.witness.read_text(encoding="utf-8")
        self.assertGreaterEqual(len(after), len(before_witness))
        self.assertIn("CERT_REVOKED", after)
        self.assertNotIn(self.secret, after)
        blocked = gate.admit_peer_message("I observe the host is localhost")
        self.assertFalse(blocked["allowed"])
        # New gate on same paths still sees turn-off + freeze.
        revived = self._gate(cert=cert)
        self.assertTrue(revived.frozen)
        self.assertIn(self.lineage, revived.revoked_ids)
        again = revived.admit_peer_message("I observe the host is localhost")
        self.assertFalse(again["allowed"])

    def test_expired_cert_refused(self):
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        cert = self._cert(
            issued_at=past - timedelta(hours=1),
            expires_at=past,
        )
        gate = self._gate(cert=cert)
        decision = gate.admit_peer_message("I observe the host is localhost")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_CERT_INVALID)

    def test_wrong_sovereign_id_refused(self):
        cert = self._cert(sovereign_id="other-sovereign")
        gate = self._gate(cert=cert)
        decision = gate.admit_peer_message("I observe the host is localhost", cert=cert)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_CERT_INVALID)
        tip = gate.witness.path.read_text(encoding="utf-8")
        self.assertIn(cert_id_of(cert), tip)


if __name__ == "__main__":
    unittest.main()
