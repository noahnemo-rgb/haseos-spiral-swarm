#!/usr/bin/env python3
"""DSM D17 — localhost Bonsai Mouth through WorldSlice (fixtures only)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from haos_dsm import (
    DEFAULT_ALLOWED_HOSTS,
    MOUTH_DEFAULT_URL,
    REASON_CERT_PARKED,
    REASON_MOUTH_UNREACHABLE,
    REASON_SCOPE_INFLATION,
    DSMGate,
    extract_hosts,
    mouth_host_token,
)
from haos_dsm_cert import REASON_CERT_INVALID, mint_haseos_cert
from haos_dsm_hook import admit_mouth, attach_gate
from inference_client import InferenceError


class MouthWorldSliceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.witness = Path(self.tmp.name) / "witness.jsonl"
        self.secret = "test-keeper-secret-d17-not-real"
        self.lineage = "queenbee.orchestrator"
        self.assertEqual(DEFAULT_ALLOWED_HOSTS, frozenset({"localhost", "127.0.0.1"}))
        self.assertEqual(mouth_host_token(MOUTH_DEFAULT_URL), "127.0.0.1")
        self.assertNotIn("8080", mouth_host_token(MOUTH_DEFAULT_URL))
        self.assertEqual(extract_hosts(MOUTH_DEFAULT_URL), ["127.0.0.1"])

    def tearDown(self):
        self.tmp.cleanup()

    def _cert(self, **kwargs):
        base = dict(
            secret=self.secret,
            sovereign_id=self.lineage,
            role="queenbee",
            slice_hosts=["127.0.0.1", "localhost"],
            slice_tools=["status"],
            hours=24.0,
        )
        base.update(kwargs)
        return mint_haseos_cert(**base)

    def _gate(self, cert=None, **kwargs):
        return DSMGate(
            lineage_id=self.lineage,
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"status", "echo"},
            cert=cert,
            **kwargs,
        )

    def test_loopback_slice_admits_mouth_host(self):
        cert = self._cert(slice_hosts=["127.0.0.1"])
        gate = self._gate(cert=cert)
        self.assertIn("127.0.0.1", gate.allowed_hosts)
        self.assertNotIn("127.0.0.1:8080", gate.allowed_hosts)
        decision = gate.admit_mouth(MOUTH_DEFAULT_URL)
        self.assertTrue(decision["allowed"], decision)
        smoked = gate.smoke_mouth(MOUTH_DEFAULT_URL, health=lambda: {"status": "ok"})
        self.assertTrue(smoked["allowed"])
        self.assertTrue(smoked["smoked"])
        self.assertEqual(smoked["health"]["status"], "ok")
        host = SimpleNamespace()
        attach_gate(
            host,
            lineage_id=self.lineage,
            witness_path=Path(self.tmp.name) / "hook_witness.jsonl",
            keeper_secret=self.secret,
            declared_tools={"status"},
            cert=self._cert(slice_hosts=["localhost", "127.0.0.1"]),
        )
        hooked = admit_mouth(host, MOUTH_DEFAULT_URL)
        self.assertTrue(hooked["allowed"], hooked)

    def test_empty_slice_hosts_parks_deny_witness_no_kill(self):
        cert = self._cert(slice_hosts=[])
        gate = self._gate(cert=cert)
        self.assertEqual(gate.allowed_hosts, set())
        decision = gate.admit_mouth(MOUTH_DEFAULT_URL)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_CERT_PARKED)
        self.assertTrue(gate.frozen)
        self.assertTrue(self.witness.is_file())
        tip = self.witness.read_text(encoding="utf-8")
        self.assertIn("CERT_PARKED", tip)
        self.assertNotIn(self.secret, tip)
        # Essence / Witness remain — turn-off, not destroy.
        self.assertTrue(self.witness.exists())

    def test_missing_slice_hosts_denied(self):
        cert = self._cert()
        del cert["slice_hosts"]
        gate = self._gate(cert=cert)
        decision = gate.admit_mouth(MOUTH_DEFAULT_URL)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_CERT_INVALID)
        self.assertIn("CERT_INVALID", self.witness.read_text(encoding="utf-8"))

    def test_saas_slice_hosts_denied_after_overlay(self):
        saas = ["openrouter", "puter", "aistudio.google", "build.nvidia"]
        cert = self._cert(slice_hosts=saas)
        gate = self._gate(cert=cert)
        self.assertEqual(gate.allowed_hosts, set())
        decision = gate.admit_mouth(MOUTH_DEFAULT_URL)
        self.assertFalse(decision["allowed"])
        self.assertIn(decision["reason"], {REASON_CERT_PARKED, REASON_SCOPE_INFLATION})
        # Even if a test gate lists SaaS on the base, overlay strips them.
        wide = self._gate(
            cert=self._cert(slice_hosts=["127.0.0.1"] + saas),
            allowed_hosts={"localhost", "127.0.0.1", *saas},
        )
        self.assertIn("127.0.0.1", wide.allowed_hosts)
        for name in saas:
            self.assertNotIn(name, wide.allowed_hosts, name)
            self.assertTrue(wide.tool_forbidden(name), name)

    def test_mouth_unreachable_fail_closed_no_saas_fallback(self):
        cert = self._cert(slice_hosts=["127.0.0.1"])
        gate = self._gate(cert=cert)
        calls = []

        def boom():
            calls.append("local")
            raise InferenceError("llama-server is not reachable")

        result = gate.smoke_mouth(MOUTH_DEFAULT_URL, health=boom)
        self.assertFalse(result["allowed"])
        self.assertFalse(result["smoked"])
        self.assertEqual(result["reason"], REASON_MOUTH_UNREACHABLE)
        self.assertEqual(calls, ["local"])
        # A Wrap/SaaS URL must not ride the successful loopback admit.
        saas = gate.smoke_mouth(
            MOUTH_DEFAULT_URL,
            health=lambda: calls.append("saas") or {"ok": True},
            client_url="https://openrouter.ai/api",
        )
        self.assertFalse(saas["allowed"])
        self.assertEqual(saas["reason"], REASON_SCOPE_INFLATION)
        self.assertNotIn("saas", calls)
        tip = self.witness.read_text(encoding="utf-8")
        self.assertIn("MOUTH_UNREACHABLE", tip)
        self.assertIn("no_saas_fallback", tip)
        self.assertNotIn(self.secret, tip)


if __name__ == "__main__":
    unittest.main()
