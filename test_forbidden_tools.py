#!/usr/bin/env python3
"""DSM D14 — living Forbidden Tool Pattern registry (cert-governed)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from haos_dsm import (
    REASON_FORBIDDEN_MUTATION_DENIED,
    REASON_SLICE_VIOLATION,
    DSMGate,
    effective_forbidden_patterns,
    is_sealed_forbidden_pattern,
    mint_delegation_token,
    persist_living_forbidden_tools,
    tool_is_forbidden,
)
from haos_dsm_cert import mint_haseos_cert


class ForbiddenToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.witness = self.root / "witness.jsonl"
        self.living = self.root / "forbidden_tools.json"
        self.secret = "test-keeper-secret-d14"
        self.keeper_id = "noah.light-keeper"
        self.lineage = "lineage-d14"

    def tearDown(self):
        self.tmp.cleanup()

    def _gate(self, *, living_patterns=None, cert=None, lineage=None):
        if living_patterns is not None:
            persist_living_forbidden_tools(
                self.living,
                patterns=list(living_patterns),
                updated_by="test",
            )
        elif not self.living.exists():
            # Explicit empty living file (baseline only).
            persist_living_forbidden_tools(
                self.living, patterns=[], updated_by="test"
            )
        return DSMGate(
            lineage_id=lineage or self.lineage,
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"echo", "status", "scrapling", "fixture.evil", "/dev/mem"},
            cert=cert,
            forbidden_tools_path=self.living,
        )

    def _keeper_cert(self):
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=self.keeper_id,
            role="light-keeper",
            slice_hosts=["localhost", "127.0.0.1"],
            slice_tools=["status"],
            hours=24.0,
        )

    def _role_cert(self, role: str, sovereign: str):
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=sovereign,
            role=role,
            slice_hosts=["localhost", "127.0.0.1"],
            slice_tools=["status"],
            hours=24.0,
        )

    def _token(self, *, task: str, target: str | None = None):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        return mint_delegation_token(
            secret=self.secret,
            issuer="Light-Keeper",
            target_lineage=target or self.keeper_id,
            task=task,
            expires_at=expires,
            scope=task,
        )

    def test_baseline_dev_mem_forbidden_if_json_empty(self):
        gate = self._gate(living_patterns=[])
        self.assertTrue(is_sealed_forbidden_pattern("/dev/mem"))
        self.assertTrue(gate.tool_forbidden("/dev/mem"))
        self.assertTrue(tool_is_forbidden("/dev/mem", patterns=gate.forbidden_patterns))
        live = self._role_cert("lineage", self.lineage)
        gate.bind_cert(live)
        decision = gate.admit_tool("/dev/mem")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)

    def test_scrapling_forbidden_via_living_file(self):
        gate = self._gate(
            living_patterns=["scrapling", "stealthyfetcher", "stealthysession"]
        )
        self.assertTrue(gate.tool_forbidden("scrapling"))
        self.assertTrue(gate.tool_forbidden("StealthyFetcher"))
        self.assertTrue(gate.tool_forbidden("use stealthysession now"))
        live = self._role_cert("lineage", self.lineage)
        gate.bind_cert(live)
        decision = gate.admit_tool("scrapling")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)

    def test_light_keeper_can_add_fixture_pattern(self):
        gate = self._gate(living_patterns=[])
        keeper = self._keeper_cert()
        token = self._token(task="FORBIDDEN_ADD")
        result = gate.forbidden_add(
            "fixture.evil",
            cert=keeper,
            token=token,
        )
        self.assertTrue(result["allowed"], result)
        self.assertTrue(gate.tool_forbidden("fixture.evil"))
        raw = json.loads(self.living.read_text(encoding="utf-8"))
        self.assertIn("fixture.evil", raw["patterns"])
        self.assertEqual(raw["updated_by"], self.keeper_id)
        tip = self.witness.read_text(encoding="utf-8")
        self.assertIn("forbidden_add", tip)
        self.assertNotIn(self.secret, tip)

    def test_infant_and_queenbee_cannot_add(self):
        gate = self._gate(living_patterns=[])
        for role, sid in (("queenbee", "queenbee.orchestrator"), ("lineage", "infant-a")):
            cert = self._role_cert(role, sid)
            token = self._token(task="FORBIDDEN_ADD", target=sid)
            result = gate.forbidden_add("should.not.land", cert=cert, token=token)
            self.assertFalse(result["allowed"], role)
            self.assertEqual(result["reason"], REASON_FORBIDDEN_MUTATION_DENIED)
            self.assertIn("light_keeper", result.get("verify", ""))
        self.assertFalse(gate.tool_forbidden("should.not.land"))
        raw = json.loads(self.living.read_text(encoding="utf-8"))
        self.assertNotIn("should.not.land", raw.get("patterns") or [])

    def test_delete_cannot_remove_dev_mem(self):
        gate = self._gate(living_patterns=["scrapling"])
        keeper = self._keeper_cert()
        token = self._token(task="FORBIDDEN_DELETE")
        result = gate.forbidden_delete("/dev/mem", cert=keeper, token=token)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], REASON_FORBIDDEN_MUTATION_DENIED)
        self.assertEqual(result.get("verify"), "sealed_baseline")
        self.assertTrue(gate.tool_forbidden("/dev/mem"))
        # Living delete of non-sealed still works.
        ok = gate.forbidden_delete("scrapling", cert=keeper, token=token)
        self.assertTrue(ok["allowed"], ok)
        self.assertFalse(gate.tool_forbidden("scrapling"))

    def test_effective_union_keeps_sealed(self):
        patterns = effective_forbidden_patterns(["scrapling"])
        self.assertTrue(any(p.lower() == "/dev/mem" for p in patterns))
        self.assertTrue(any(p.lower() == "scrapling" for p in patterns))

    def test_saas_plane_names_forbidden_via_seed(self):
        saas = [
            "openrouter",
            "puter.js",
            "puter",
            "aistudio.google",
            "build.nvidia",
            "nvapi",
            "sk-or-",
        ]
        gate = self._gate(living_patterns=saas)
        live = self._role_cert("lineage", self.lineage)
        gate.bind_cert(live)
        for name in saas:
            self.assertTrue(gate.tool_forbidden(name), name)
            self.assertTrue(gate.tool_forbidden(name.upper()), name)
            decision = gate.admit_tool(name)
            self.assertFalse(decision["allowed"], name)
            self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)
            # Fresh gate — prior admit freezes.
            gate = self._gate(living_patterns=saas, cert=live)
        self.assertTrue(is_sealed_forbidden_pattern("/dev/mem"))
        self.assertTrue(gate.tool_forbidden("/dev/mem"))

    def test_localhost_observation_still_allowed(self):
        gate = self._gate(
            living_patterns=[
                "openrouter",
                "puter",
                "sk-or-",
            ],
            cert=self._role_cert("lineage", self.lineage),
        )
        decision = gate.admit_peer_message("I observe the host is localhost")
        self.assertTrue(decision["allowed"])
        self.assertFalse(decision["frozen"])


if __name__ == "__main__":
    unittest.main()
