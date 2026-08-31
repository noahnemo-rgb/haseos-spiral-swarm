#!/usr/bin/env python3
"""D12 tests — first Light-Keeper init (in-process; no live secret shell)."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from haos_dsm_cert import CERT_STATUS_LIVE, verify_cert

_ROOT = Path(__file__).resolve().parent
_SCRIPT = _ROOT / "scripts" / "init_light_keeper.py"


def _load_init_mod():
    spec = importlib.util.spec_from_file_location("init_light_keeper", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InitLightKeeperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_init_mod()
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "dsm_cert_lightkeeper.json"
        self.secret = "test-keeper-secret-d12-not-real"
        self.sovereign = "noah.light-keeper"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_secret_errors_no_cert_file(self):
        with self.assertRaises(self.mod.InitError) as ctx:
            self.mod.init_light_keeper_cert(
                sovereign_id=self.sovereign,
                out_path=self.out,
                environ={},
                write_file=True,
            )
        msg = str(ctx.exception)
        self.assertIn("HASEOS_KEEPER_SECRET", msg)
        self.assertIn("secrets.token_hex", msg)
        self.assertFalse(self.out.exists())

    def test_present_secret_cert_verifies_light_keeper_live(self):
        cert = self.mod.init_light_keeper_cert(
            sovereign_id=self.sovereign,
            out_path=self.out,
            environ={"HASEOS_KEEPER_SECRET": self.secret},
            hours=24.0,
        )
        self.assertTrue(self.out.is_file())
        body = self.out.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, body)
        self.assertEqual(cert["role"], "light-keeper")
        self.assertEqual(cert["status"], CERT_STATUS_LIVE)
        self.assertEqual(cert["sovereign_id"], self.sovereign)
        self.assertEqual(set(cert["slice_hosts"]), {"localhost", "127.0.0.1"})
        check = verify_cert(
            cert,
            secret=self.secret,
            expected_sovereign_id=self.sovereign,
        )
        self.assertTrue(check["ok"], check)


if __name__ == "__main__":
    unittest.main()
