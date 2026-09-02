#!/usr/bin/env python3
"""D19 tests — Infant cert at promotion (fixtures only; no living repo certs)."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import usb_state
from haos_dsm import REASON_SLICE_VIOLATION, DSMGate
from haos_dsm_cert import CERT_STATUS_LIVE, mint_haseos_cert, verify_cert
from haos_dsm_infant import (
    INFANT_CERT_FILENAME,
    infant_slice_fits_chain,
    infant_slice_fits_senior,
    place_infant_cert_beside_usb,
)
from haos_dsm_usb import sibling_witness_path

_ROOT = Path(__file__).resolve().parent
_SCRIPT = _ROOT / "scripts" / "init_infant_cert.py"


def _load_init_mod():
    spec = importlib.util.spec_from_file_location("init_infant_cert", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InitInfantCertTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_init_mod()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "dsm_cert_infant.json"
        self.witness = self.root / "witness.jsonl"
        self.secret = "test-keeper-secret-d19-not-real"
        self.sovereign = "infant.promoted-a"
        self.senior_id = "senior.promoted-a"
        self.qb_id = "queenbee.orchestrator"

    def tearDown(self):
        self.tmp.cleanup()

    def _senior(self, hosts=None, tools=None):
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=self.senior_id,
            role="senior",
            slice_hosts=list(hosts or ["localhost", "127.0.0.1"]),
            slice_tools=list(tools or ["status", "echo"]),
            hours=24.0,
        )

    def _queenbee(self, hosts=None, tools=None):
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=self.qb_id,
            role="queenbee",
            slice_hosts=list(hosts or ["localhost", "127.0.0.1"]),
            slice_tools=list(tools or ["status", "echo", "wading_pool.select"]),
            hours=24.0,
        )

    def test_missing_secret_no_file(self):
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_infant_cert(
                sovereign_id=self.sovereign,
                senior_cert=self._senior(),
                out_path=self.out,
                environ={},
                write_file=True,
            )
        self.assertIn("HASEOS_KEEPER_SECRET", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_live_infant_cert_verifies(self):
        cert = self.mod.init_infant_cert(
            sovereign_id=self.sovereign,
            senior_cert=self._senior(tools=["status"]),
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
        )
        self.assertTrue(self.out.is_file())
        body = self.out.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, body)
        self.assertEqual(cert["role"], "infant")
        self.assertEqual(cert["status"], CERT_STATUS_LIVE)
        self.assertEqual(set(cert["slice_hosts"]), {"localhost", "127.0.0.1"})
        self.assertEqual(cert["slice_tools"], ["status"])
        self.assertNotIn("127.0.0.1:8080", cert["slice_hosts"])
        check = verify_cert(
            cert, secret=self.secret, expected_sovereign_id=self.sovereign
        )
        self.assertTrue(check["ok"], check)

    def test_empty_slice_hosts_stay_empty(self):
        minted = mint_haseos_cert(
            secret=self.secret,
            sovereign_id=self.sovereign,
            role="infant",
            slice_hosts=[],
            slice_tools=["status"],
            hours=24.0,
        )
        self.assertEqual(minted["slice_hosts"], [])
        with self.assertRaises(self.mod.InitError):
            self.mod.init_infant_cert(
                sovereign_id=self.sovereign,
                senior_cert=self._senior(),
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                hosts=[],
            )
        self.assertFalse(self.out.exists())

    def test_infant_tools_not_subset_of_senior_refused(self):
        senior = self._senior(tools=["status"])
        senior_path = self.root / "dsm_cert_senior_fixture.json"
        senior_path.write_text(json.dumps(senior), encoding="utf-8")
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_infant_cert(
                sovereign_id=self.sovereign,
                senior_cert_path=senior_path,
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                tools=["status", "echo"],
            )
        self.assertIn("⊆", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_infant_hosts_subset_of_senior_accepted(self):
        senior = self._senior(hosts=["localhost", "127.0.0.1"], tools=["status"])
        self.assertTrue(
            infant_slice_fits_senior(
                {"slice_hosts": ["localhost"], "slice_tools": ["status"]},
                senior,
            )
        )
        cert = self.mod.init_infant_cert(
            sovereign_id=self.sovereign,
            senior_cert=senior,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hosts=["localhost"],
            tools=["status"],
        )
        self.assertEqual(cert["slice_hosts"], ["localhost"])
        self.assertTrue(self.out.is_file())

    def test_place_beside_usb_witness_notes_no_secret(self):
        cert = self.mod.init_infant_cert(
            sovereign_id=self.sovereign,
            senior_cert=self._senior(tools=["status"]),
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
        )
        usb_path = self.root / "node-infant.json"
        state = usb_state.create_empty("node-infant", mode="file", path=str(usb_path))
        usb_state.save(state, usb_path)
        dest = place_infant_cert_beside_usb(
            usb_path,
            cert,
            primary_witness=self.witness,
        )
        self.assertEqual(dest.name, INFANT_CERT_FILENAME)
        self.assertTrue(dest.name.startswith("dsm_cert"))
        self.assertTrue(dest.name.endswith(".json"))
        sibling = sibling_witness_path(usb_path)
        self.assertEqual(sibling.name, "node-infant.json.dsm_witness.jsonl")
        self.assertTrue(sibling.is_file())
        loaded = json.loads(usb_path.read_text(encoding="utf-8"))
        note = loaded["notes"]["dsm_cert_infant"]
        self.assertEqual(note["role"], "infant")
        self.assertEqual(note["sovereign_id"], self.sovereign)
        self.assertEqual(note["path"], str(dest))
        self.assertIn("cert_id", note)
        usb_text = usb_path.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, usb_text)
        self.assertNotIn(self.secret, dest.read_text(encoding="utf-8"))
        self.assertNotIn("signature", json.dumps(note))

    def test_role_senior_rejected(self):
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_infant_cert(
                sovereign_id=self.sovereign,
                senior_cert=self._senior(),
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                role="senior",
            )
        self.assertIn("D18", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_forbidden_infant_tools_not_in_worldslice(self):
        senior = self._senior(tools=["status", "openrouter", "scrapling"])
        cert = self.mod.init_infant_cert(
            sovereign_id=self.sovereign,
            senior_cert=senior,
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

    def test_chain_infant_subset_senior_subset_queenbee_accepted(self):
        senior = self._senior(tools=["status", "echo"])
        queenbee = self._queenbee(tools=["status", "echo", "wading_pool.select"])
        self.assertTrue(
            infant_slice_fits_chain(
                {"slice_hosts": ["localhost"], "slice_tools": ["status"]},
                senior,
                queenbee,
            )
        )
        cert = self.mod.init_infant_cert(
            sovereign_id=self.sovereign,
            senior_cert=senior,
            queenbee_cert=queenbee,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hosts=["localhost"],
            tools=["status"],
        )
        self.assertEqual(cert["role"], "infant")
        self.assertTrue(self.out.is_file())

    def test_chain_fail_tool_on_senior_not_on_queenbee(self):
        senior = self._senior(tools=["status", "echo"])
        queenbee = self._queenbee(tools=["status"])
        qb_path = self.root / "dsm_cert_queenbee_fixture.json"
        qb_path.write_text(json.dumps(queenbee), encoding="utf-8")
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_infant_cert(
                sovereign_id=self.sovereign,
                senior_cert=senior,
                queenbee_cert_path=qb_path,
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                tools=["echo"],
            )
        self.assertIn("⊆", str(ctx.exception))
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
