#!/usr/bin/env python3
"""D18 tests — Senior cert at promotion (fixtures only; no living repo certs)."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import usb_state
from haos_dsm import REASON_SLICE_VIOLATION, DSMGate
from haos_dsm_cert import CERT_STATUS_LIVE, mint_haseos_cert, verify_cert
from haos_dsm_senior import (
    SENIOR_CERT_FILENAME,
    place_senior_cert_beside_usb,
    senior_slice_fits_queenbee,
)
from haos_dsm_usb import sibling_witness_path

_ROOT = Path(__file__).resolve().parent
_SCRIPT = _ROOT / "scripts" / "init_senior_cert.py"


def _load_init_mod():
    spec = importlib.util.spec_from_file_location("init_senior_cert", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InitSeniorCertTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_init_mod()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "dsm_cert_senior.json"
        self.witness = self.root / "witness.jsonl"
        self.secret = "test-keeper-secret-d18-not-real"
        self.sovereign = "senior.promoted-a"
        self.qb_sovereign = "queenbee.orchestrator"

    def tearDown(self):
        self.tmp.cleanup()

    def _queenbee(self, hosts=None, tools=None):
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=self.qb_sovereign,
            role="queenbee",
            slice_hosts=list(hosts or ["localhost", "127.0.0.1"]),
            slice_tools=list(tools or ["status", "echo"]),
            hours=24.0,
        )

    def test_missing_secret_no_file_written(self):
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_senior_cert(
                sovereign_id=self.sovereign,
                out_path=self.out,
                environ={},
                write_file=True,
            )
        self.assertIn("HASEOS_KEEPER_SECRET", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_live_senior_cert_verifies(self):
        cert = self.mod.init_senior_cert(
            sovereign_id=self.sovereign,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
        )
        self.assertTrue(self.out.is_file())
        body = self.out.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, body)
        self.assertEqual(cert["role"], "senior")
        self.assertEqual(cert["status"], CERT_STATUS_LIVE)
        self.assertEqual(set(cert["slice_hosts"]), {"localhost", "127.0.0.1"})
        self.assertEqual(cert["slice_tools"], ["status"])
        self.assertNotIn("127.0.0.1:8080", cert["slice_hosts"])
        check = verify_cert(
            cert, secret=self.secret, expected_sovereign_id=self.sovereign
        )
        self.assertTrue(check["ok"], check)

    def test_empty_slice_hosts_stay_empty(self):
        cert = self.mod.init_senior_cert(
            sovereign_id=self.sovereign,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hosts=[],
            hours=24.0,
        )
        self.assertEqual(cert["slice_hosts"], [])
        self.assertNotEqual(set(cert["slice_hosts"]), {"localhost", "127.0.0.1"})

    def test_senior_tools_not_subset_of_queenbee_refused(self):
        qb = self._queenbee(tools=["status"])
        qb_path = self.root / "dsm_cert_queenbee_fixture.json"
        qb_path.write_text(json.dumps(qb), encoding="utf-8")
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_senior_cert(
                sovereign_id=self.sovereign,
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                tools=["status", "echo"],
                queenbee_cert_path=qb_path,
            )
        self.assertIn("⊆", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_senior_hosts_subset_of_queenbee_accepted(self):
        qb = self._queenbee(hosts=["localhost", "127.0.0.1"], tools=["status"])
        self.assertTrue(
            senior_slice_fits_queenbee(
                {"slice_hosts": ["localhost"], "slice_tools": ["status"]},
                qb,
            )
        )
        cert = self.mod.init_senior_cert(
            sovereign_id=self.sovereign,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hosts=["localhost"],
            tools=["status"],
            queenbee_cert=qb,
        )
        self.assertEqual(cert["slice_hosts"], ["localhost"])
        self.assertTrue(self.out.is_file())

    def test_place_beside_usb_witness_notes_no_secret(self):
        cert = self.mod.init_senior_cert(
            sovereign_id=self.sovereign,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
        )
        usb_path = self.root / "node-senior.json"
        state = usb_state.create_empty("node-senior", mode="file", path=str(usb_path))
        usb_state.save(state, usb_path)
        dest = place_senior_cert_beside_usb(
            usb_path,
            cert,
            primary_witness=self.witness,
        )
        self.assertEqual(dest.name, SENIOR_CERT_FILENAME)
        self.assertTrue(dest.name.startswith("dsm_cert"))
        self.assertTrue(dest.name.endswith(".json"))
        sibling = sibling_witness_path(usb_path)
        self.assertEqual(sibling.name, "node-senior.json.dsm_witness.jsonl")
        self.assertTrue(sibling.is_file())
        loaded = json.loads(usb_path.read_text(encoding="utf-8"))
        note = loaded["notes"]["dsm_cert_senior"]
        self.assertEqual(note["role"], "senior")
        self.assertEqual(note["sovereign_id"], self.sovereign)
        self.assertEqual(note["path"], str(dest))
        self.assertIn("cert_id", note)
        usb_text = usb_path.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, usb_text)
        self.assertNotIn(self.secret, dest.read_text(encoding="utf-8"))
        self.assertNotIn("signature", json.dumps(note))

    def test_role_infant_rejected(self):
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_senior_cert(
                sovereign_id=self.sovereign,
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                role="infant",
            )
        self.assertIn("D19", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_forbidden_senior_tools_not_in_worldslice(self):
        cert = self.mod.init_senior_cert(
            sovereign_id=self.sovereign,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            tools=["status", "openrouter", "scrapling"],
            hours=24.0,
        )
        gate = DSMGate(
            lineage_id=self.sovereign,
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"status", "openrouter", "scrapling", "echo"},
            cert=cert,
        )
        self.assertIn("status", gate.declared_tools)
        self.assertNotIn("openrouter", gate.declared_tools)
        self.assertNotIn("scrapling", gate.declared_tools)
        for name in ("openrouter", "scrapling"):
            g = DSMGate(
                lineage_id=self.sovereign,
                witness_path=self.witness,
                keeper_secret=self.secret,
                declared_tools={"status", "openrouter", "scrapling"},
                cert=cert,
            )
            decision = g.admit_tool(name)
            self.assertFalse(decision["allowed"], name)
            self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)


if __name__ == "__main__":
    unittest.main()
