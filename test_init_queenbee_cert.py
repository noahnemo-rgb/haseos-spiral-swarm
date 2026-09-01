#!/usr/bin/env python3
"""D13 tests — QueenBee cert mint + hook load-if-present (in-process)."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import haos_dsm_hook
from haos_dsm_cert import CERT_STATUS_LIVE, REASON_CERT_INVALID, verify_cert

_ROOT = Path(__file__).resolve().parent
_SCRIPT = _ROOT / "scripts" / "init_queenbee_cert.py"


def _load_init_mod():
    spec = importlib.util.spec_from_file_location("init_queenbee_cert", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InitQueenbeeCertTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_init_mod()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "dsm_cert_queenbee.json"
        self.witness = self.root / "witness.jsonl"
        self.secret = "test-keeper-secret-d13-not-real"
        self.sovereign = "queenbee.orchestrator"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_secret_no_cert_file(self):
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_queenbee_cert(
                sovereign_id=self.sovereign,
                out_path=self.out,
                environ={},
                write_file=True,
            )
        self.assertIn("HASEOS_KEEPER_SECRET", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_present_secret_role_queenbee_verifies(self):
        cert = self.mod.init_queenbee_cert(
            sovereign_id=self.sovereign,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
            tools=["status", "wading_pool.select"],
        )
        self.assertTrue(self.out.is_file())
        body = self.out.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, body)
        self.assertEqual(cert["role"], "queenbee")
        self.assertEqual(cert["status"], CERT_STATUS_LIVE)
        self.assertEqual(cert["sovereign_id"], self.sovereign)
        check = verify_cert(
            cert, secret=self.secret, expected_sovereign_id=self.sovereign
        )
        self.assertTrue(check["ok"], check)

    def test_hook_with_cert_path_admits_observation(self):
        cert = self.mod.init_queenbee_cert(
            sovereign_id=self.sovereign,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
            tools=["status"],
        )
        host = SimpleNamespace()
        haos_dsm_hook.attach_gate(
            host,
            lineage_id=self.sovereign,
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"status", "echo"},
            cert_path=self.out,
        )
        self.assertIsNotNone(host._dsm_cert)
        self.assertFalse(hasattr(host, "HASEOS_KEEPER_SECRET"))
        self.assertNotIn("keeper_secret", host.__dict__)
        decision = haos_dsm_hook.admit_peer_message(
            host, "I observe the host is localhost"
        )
        self.assertTrue(decision["allowed"], decision)
        self.assertEqual(host._dsm_cert.get("role"), "queenbee")
        self.assertEqual(cert["role"], "queenbee")

    def test_hook_without_cert_file_refuses(self):
        missing = self.root / "no_such_cert.json"
        host = SimpleNamespace()
        haos_dsm_hook.attach_gate(
            host,
            lineage_id=self.sovereign,
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"status"},
            cert_path=missing,
        )
        self.assertIsNone(host._dsm_cert)
        decision = haos_dsm_hook.admit_peer_message(
            host, "I observe the host is localhost"
        )
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_CERT_INVALID)


if __name__ == "__main__":
    unittest.main()
