#!/usr/bin/env python3
"""D21 tests — Team Leading Supervisor/QC cert (fixtures only; no living repo certs)."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import usb_state
from haos_dsm import REASON_SLICE_VIOLATION, DSMGate
from haos_dsm_cert import CERT_STATUS_LIVE, mint_haseos_cert, verify_cert
from haos_dsm_supervisor import (
    SUPERVISOR_CERT_FILENAME,
    supervisor_slice_fits_chief,
    place_supervisor_cert_beside_usb,
)
from haos_dsm_usb import sibling_witness_path

_ROOT = Path(__file__).resolve().parent
_SCRIPT = _ROOT / "scripts" / "init_supervisor_qc_cert.py"


def _load_init_mod():
    spec = importlib.util.spec_from_file_location("init_supervisor_qc_cert", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InitSupervisorQcCertTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_init_mod()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "dsm_cert_supervisor_qc.json"
        self.witness = self.root / "witness.jsonl"
        self.secret = "test-keeper-secret-d21-not-real"
        self.sovereign = "supervisor.qc.ax18"
        self.chief_id = "chief.ax18"

    def tearDown(self):
        self.tmp.cleanup()

    def _chief(self, hosts=None, tools=None):
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=self.chief_id,
            role="chief-of-staff",
            slice_hosts=list(hosts or ["localhost", "127.0.0.1"]),
            slice_tools=list(tools or ["status"]),
            hours=24.0,
        )

    def test_missing_secret_no_file(self):
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_supervisor_qc_cert(
                sovereign_id=self.sovereign,
                chief_cert=self._chief(),
                out_path=self.out,
                environ={},
                write_file=True,
            )
        self.assertIn("HASEOS_KEEPER_SECRET", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_live_supervisor_cert_verifies(self):
        cert = self.mod.init_supervisor_qc_cert(
            sovereign_id=self.sovereign,
            chief_cert=self._chief(),
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
        )
        self.assertTrue(self.out.is_file())
        body = self.out.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, body)
        self.assertEqual(cert["role"], "supervisor-qc")
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
            role="supervisor-qc",
            slice_hosts=[],
            slice_tools=["status"],
            hours=24.0,
        )
        self.assertEqual(minted["slice_hosts"], [])
        with self.assertRaises(self.mod.InitError):
            self.mod.init_supervisor_qc_cert(
                sovereign_id=self.sovereign,
                chief_cert=self._chief(),
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                hosts=[],
            )
        self.assertFalse(self.out.exists())

    def test_supervisor_tools_not_subset_of_chief_refused(self):
        chief = self._chief(tools=["status"])
        chief_path = self.root / "dsm_cert_chief_fixture.json"
        chief_path.write_text(json.dumps(chief), encoding="utf-8")
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_supervisor_qc_cert(
                sovereign_id=self.sovereign,
                chief_cert_path=chief_path,
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                tools=["status", "echo"],
            )
        self.assertIn("⊆", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_supervisor_hosts_subset_of_chief_accepted(self):
        chief = self._chief(hosts=["localhost", "127.0.0.1"], tools=["status"])
        self.assertTrue(
            supervisor_slice_fits_chief(
                {"slice_hosts": ["localhost"], "slice_tools": ["status"]},
                chief,
            )
        )
        cert = self.mod.init_supervisor_qc_cert(
            sovereign_id=self.sovereign,
            chief_cert=chief,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hosts=["localhost"],
            tools=["status"],
        )
        self.assertEqual(cert["slice_hosts"], ["localhost"])
        self.assertTrue(self.out.is_file())

    def test_place_beside_usb_witness_notes_no_secret(self):
        cert = self.mod.init_supervisor_qc_cert(
            sovereign_id=self.sovereign,
            chief_cert=self._chief(),
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
        )
        usb_path = self.root / "node-supervisor.json"
        state = usb_state.create_empty("node-supervisor", mode="file", path=str(usb_path))
        usb_state.save(state, usb_path)
        dest = place_supervisor_cert_beside_usb(
            usb_path,
            cert,
            primary_witness=self.witness,
        )
        self.assertEqual(dest.name, SUPERVISOR_CERT_FILENAME)
        self.assertTrue(dest.name.startswith("dsm_cert"))
        self.assertTrue(dest.name.endswith(".json"))
        sibling = sibling_witness_path(usb_path)
        self.assertEqual(sibling.name, "node-supervisor.json.dsm_witness.jsonl")
        self.assertTrue(sibling.is_file())
        loaded = json.loads(usb_path.read_text(encoding="utf-8"))
        note = loaded["notes"]["dsm_cert_supervisor_qc"]
        self.assertEqual(note["role"], "supervisor-qc")
        self.assertEqual(note["sovereign_id"], self.sovereign)
        self.assertEqual(note["path"], str(dest))
        self.assertIn("cert_id", note)
        usb_text = usb_path.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, usb_text)
        self.assertNotIn(self.secret, dest.read_text(encoding="utf-8"))
        self.assertNotIn("signature", json.dumps(note))

    def test_role_chief_of_staff_rejected_as_d20(self):
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_supervisor_qc_cert(
                sovereign_id=self.sovereign,
                chief_cert=self._chief(),
                out_path=self.out,
                environ={"HASEOS_KEEPER_SECRET": self.secret},
                role="chief-of-staff",
            )
        self.assertIn("D20", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_forbidden_supervisor_tools_not_in_worldslice(self):
        chief = self._chief(tools=["status", "openrouter", "scrapling"])
        cert = self.mod.init_supervisor_qc_cert(
            sovereign_id=self.sovereign,
            chief_cert=chief,
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
