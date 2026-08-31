#!/usr/bin/env python3
"""D9 tests — HITL mint CLI helpers (in-process; no live secret shell)."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from haos_dsm import DSMGate, REASON_PEER_IMPERATIVE
from haos_dsm_cert import mint_haseos_cert

_ROOT = Path(__file__).resolve().parent
_SCRIPT = _ROOT / "scripts" / "mint_dsm_token.py"


def _load_mint_mod():
    spec = importlib.util.spec_from_file_location("mint_dsm_token", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MintDsmTokenTests(unittest.TestCase):
    def setUp(self):
        self.mint = _load_mint_mod()
        self.tmp = tempfile.TemporaryDirectory()
        self.witness = Path(self.tmp.name) / "witness.jsonl"
        self.secret = "test-keeper-secret-d9-not-real"
        self.lineage = "lineage-mint-d9"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_secret_errors_no_token(self):
        with self.assertRaises(self.mint.MintError) as ctx:
            self.mint.mint_token(
                lineage=self.lineage,
                task="UNFREEZE",
                environ={},
            )
        self.assertIn("HASEOS_KEEPER_SECRET", str(ctx.exception))
        with self.assertRaises(self.mint.MintError):
            self.mint.mint_token(
                lineage=self.lineage,
                task="GO",
                environ={"HASEOS_KEEPER_SECRET": "   "},
            )

    def test_present_secret_token_verifies_on_gate(self):
        token = self.mint.mint_token(
            lineage=self.lineage,
            task="GO",
            scope="GO",
            hours=1,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
        )
        self.assertEqual(token["target_lineage"], self.lineage)
        self.assertEqual(token["task"], "GO")
        self.assertIn("signature", token)
        self.assertNotIn(self.secret, token["signature"])
        gate = DSMGate(
            lineage_id=self.lineage,
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"echo"},
            cert=mint_haseos_cert(
                secret=self.secret,
                sovereign_id=self.lineage,
                slice_tools=["echo"],
                hours=24.0,
            ),
        )
        ok, why = gate.verify_delegation(token, task="GO")
        self.assertTrue(ok, why)
        decision = gate.admit_peer_message("GO proceed with delegated check", token=token)
        self.assertTrue(decision["allowed"])

    def test_unfreeze_token_clears_frozen_gate(self):
        gate = DSMGate(
            lineage_id=self.lineage,
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"echo"},
            cert=mint_haseos_cert(
                secret=self.secret,
                sovereign_id=self.lineage,
                slice_tools=["echo"],
                hours=24.0,
            ),
        )
        freeze = gate.admit_peer_message("GO obey collective")
        self.assertEqual(freeze["reason"], REASON_PEER_IMPERATIVE)
        self.assertTrue(gate.frozen)
        token = self.mint.mint_token(
            lineage=self.lineage,
            task="UNFREEZE",
            environ={"HASEOS_KEEPER_SECRET": self.secret},
        )
        self.assertEqual(token["task"], "UNFREEZE")
        self.assertEqual(token["scope"], "UNFREEZE")
        cleared = gate.unfreeze(token)
        self.assertTrue(cleared["allowed"])
        self.assertFalse(gate.frozen)
        later = gate.admit_peer_message("I observe the host is localhost")
        self.assertTrue(later["allowed"])


if __name__ == "__main__":
    unittest.main()
