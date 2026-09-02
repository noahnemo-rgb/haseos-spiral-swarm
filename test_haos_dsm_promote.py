#!/usr/bin/env python3
"""D22 tests — /promote cert write (fixtures only; no QueenBee, no torch)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import usb_state
from haos_dsm_cert import mint_haseos_cert
from haos_dsm_infant import INFANT_CERT_FILENAME
from haos_dsm_promote import (
    REASON_SECRET_MISSING,
    REASON_SENIOR_CERT_MISSING,
    REASON_SLICE_NOT_SUBSET,
    promote_to_usb_cert,
)
from haos_dsm_senior import SENIOR_CERT_FILENAME


class PromoteToUsbCertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.secret = "test-keeper-secret-d22-not-real"
        self.infant_id = "infant.promoted-d22"
        self.senior_id = "senior.promoted-d22"
        self.qb_id = "queenbee.orchestrator"
        self.env = {"HASEOS_KEEPER_SECRET": self.secret}

    def tearDown(self):
        self.tmp.cleanup()

    def _write_cert(self, name: str, cert: dict) -> Path:
        dest = self.root / name
        dest.write_text(json.dumps(cert), encoding="utf-8")
        return dest

    def _senior(self, hosts=None, tools=None) -> dict:
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=self.senior_id,
            role="senior",
            slice_hosts=list(hosts or ["localhost", "127.0.0.1"]),
            slice_tools=list(tools or ["status"]),
            hours=24.0,
        )

    def _queenbee(self, hosts=None, tools=None) -> dict:
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=self.qb_id,
            role="queenbee",
            slice_hosts=list(hosts or ["localhost", "127.0.0.1"]),
            slice_tools=list(tools or ["status", "echo"]),
            hours=24.0,
        )

    def _usb(self, node_id: str = "node-d22") -> Path:
        path = self.root / f"{node_id}.json"
        state = usb_state.create_empty(node_id, mode="file", path=str(path))
        usb_state.save(state, path)
        return path

    def test_missing_secret_no_file(self):
        dest = self.root / INFANT_CERT_FILENAME
        self._write_cert(SENIOR_CERT_FILENAME, self._senior())
        result = promote_to_usb_cert(
            sovereign_id=self.infant_id,
            out_path=dest,
            repo_root=self.root,
            environ={},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], REASON_SECRET_MISSING)
        self.assertFalse(result["cert_written"])
        self.assertFalse(dest.exists())

    def test_infant_success_fixture_senior_usb_notes_no_secret(self):
        senior_path = self._write_cert(SENIOR_CERT_FILENAME, self._senior())
        usb_path = self._usb()
        dest = self.root / INFANT_CERT_FILENAME
        result = promote_to_usb_cert(
            sovereign_id=self.infant_id,
            role="infant",
            reason="HITL fixture promote",
            senior_cert_path=senior_path,
            usb_image=usb_path,
            out_path=dest,
            repo_root=self.root,
            environ=self.env,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(Path(result["dest"]).name, INFANT_CERT_FILENAME)
        self.assertTrue(Path(result["dest"]).is_file())
        loaded = json.loads(usb_path.read_text(encoding="utf-8"))
        note = loaded["notes"]["dsm_cert_infant"]
        self.assertEqual(note["role"], "infant")
        self.assertEqual(note["sovereign_id"], self.infant_id)
        usb_text = usb_path.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, usb_text)
        self.assertNotIn(self.secret, dest.read_text(encoding="utf-8"))
        self.assertEqual(loaded["notes"].get("dsm_promote_reason"), "HITL fixture promote")

    def test_infant_refused_when_senior_cert_missing(self):
        dest = self.root / INFANT_CERT_FILENAME
        result = promote_to_usb_cert(
            sovereign_id=self.infant_id,
            role="infant",
            out_path=dest,
            repo_root=self.root,
            environ=self.env,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], REASON_SENIOR_CERT_MISSING)
        self.assertFalse(result["cert_written"])
        self.assertFalse(dest.exists())

    def test_senior_success_fixture_queenbee(self):
        qb_path = self._write_cert("dsm_cert_queenbee.json", self._queenbee())
        dest = self.root / SENIOR_CERT_FILENAME
        result = promote_to_usb_cert(
            sovereign_id=self.senior_id,
            role="senior",
            queenbee_cert_path=qb_path,
            out_path=dest,
            repo_root=self.root,
            environ=self.env,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["role"], "senior")
        self.assertEqual(Path(result["dest"]).name, SENIOR_CERT_FILENAME)
        self.assertTrue(dest.is_file())
        body = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(body["role"], "senior")
        self.assertNotIn(self.secret, dest.read_text(encoding="utf-8"))

    def test_infant_tools_not_subset_of_senior_refused(self):
        senior_path = self._write_cert(
            SENIOR_CERT_FILENAME, self._senior(tools=["status"])
        )
        dest = self.root / INFANT_CERT_FILENAME
        result = promote_to_usb_cert(
            sovereign_id=self.infant_id,
            role="infant",
            senior_cert_path=senior_path,
            out_path=dest,
            repo_root=self.root,
            environ=self.env,
            tools=["status", "echo"],
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], REASON_SLICE_NOT_SUBSET)
        self.assertFalse(result["cert_written"])
        self.assertFalse(dest.exists())

    def test_senior_path_uses_dsm_cert_senior_json(self):
        self._write_cert("dsm_cert_queenbee.json", self._queenbee())
        result = promote_to_usb_cert(
            sovereign_id=self.senior_id,
            role="senior",
            repo_root=self.root,
            environ=self.env,
        )
        self.assertTrue(result["ok"], result)
        dest = Path(result["dest"])
        self.assertEqual(dest.name, SENIOR_CERT_FILENAME)
        self.assertEqual(dest, self.root / SENIOR_CERT_FILENAME)

    def test_return_dict_has_no_signature_or_secret(self):
        self._write_cert(SENIOR_CERT_FILENAME, self._senior())
        dest = self.root / INFANT_CERT_FILENAME
        result = promote_to_usb_cert(
            sovereign_id=self.infant_id,
            senior_cert_path=self.root / SENIOR_CERT_FILENAME,
            out_path=dest,
            repo_root=self.root,
            environ=self.env,
        )
        self.assertTrue(result["ok"], result)
        dumped = json.dumps(result)
        self.assertNotIn("signature", result)
        self.assertNotIn("signature", dumped)
        self.assertNotIn(self.secret, dumped)
        self.assertIn("cert_id", result)
        self.assertIn("dest", result)
        self.assertIn("role", result)


if __name__ == "__main__":
    unittest.main()
