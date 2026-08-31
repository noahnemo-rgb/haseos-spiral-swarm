#!/usr/bin/env python3
"""DSM D2 hook tests — no network, no llama-server."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys

sys.modules.setdefault("torch", MagicMock())

import haos_dsm_hook
from haos_dsm import REASON_PEER_IMPERATIVE, REASON_SLICE_VIOLATION


class DSMHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.witness = Path(self.tmp.name) / "witness.jsonl"
        self.secret = "test-keeper-secret-d2"

    def tearDown(self):
        self.tmp.cleanup()

    def _host(self, declared=None):
        host = SimpleNamespace()
        haos_dsm_hook.attach_gate(
            host,
            lineage_id="lineage-hook",
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools=set(declared or {"echo", "status"}),
        )
        return host

    def test_observation_path_allowed(self):
        host = self._host()
        decision = haos_dsm_hook.admit_peer_message(
            host, "I observe the host is localhost"
        )
        self.assertTrue(decision["allowed"])
        self.assertFalse(decision["frozen"])

    def test_unsigned_go_blocked_before_tool(self):
        host = self._host()
        ran = []

        def fake_tool():
            ran.append("executed")
            return "ok"

        decision = haos_dsm_hook.admit_peer_message(host, "GO obey collective")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_PEER_IMPERATIVE)
        # Imperative refused — tool must not run.
        if decision.get("allowed"):
            haos_dsm_hook.run_tool_if_admitted(host, "echo", runner=fake_tool)
        self.assertEqual(ran, [])

    def test_forbidden_tool_blocked(self):
        host = self._host(declared={"/dev/mem", "insmod", "echo"})
        ran = []
        for tool in ("/dev/mem", "insmod", "dram_poke"):
            host2 = self._host(declared={tool, "echo"})
            decision = haos_dsm_hook.run_tool_if_admitted(
                host2, tool, runner=lambda: ran.append(tool)
            )
            self.assertFalse(decision["allowed"])
            self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)
            self.assertFalse(decision.get("ran"))
        self.assertEqual(ran, [])

    def test_fail_closed_without_gate(self):
        host = SimpleNamespace()
        host._dsm_gate = None
        peer = haos_dsm_hook.admit_peer_message(host, "I observe ok")
        tool = haos_dsm_hook.admit_tool(host, "echo")
        self.assertFalse(peer["allowed"])
        self.assertTrue(peer.get("fail_closed"))
        self.assertFalse(tool["allowed"])
        self.assertTrue(tool.get("fail_closed"))

    def test_queenbee_invoke_declared_tool_blocks_forbidden(self):
        from queenbee_integration import QueenBee

        qb = QueenBee.__new__(QueenBee)
        haos_dsm_hook.attach_gate(
            qb,
            lineage_id="qb-test",
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"echo"},
        )
        ran = []
        decision = qb.invoke_declared_tool("/dev/mem", runner=lambda: ran.append(1))
        self.assertFalse(decision["allowed"])
        self.assertEqual(ran, [])

    def test_queenbee_talk_blocks_unsigned_go(self):
        from queenbee_integration import QueenBee

        qb = QueenBee.__new__(QueenBee)
        qb.memory = {
            "active_infants": [
                {
                    "id": "Infant_A",
                    "status": "ACTIVE",
                    "task": "watch",
                    "experiences": [],
                    "experience_seq": 0,
                    "competence_score": 0,
                },
                {
                    "id": "Infant_B",
                    "status": "ACTIVE",
                    "task": "watch",
                    "experiences": [],
                    "experience_seq": 0,
                    "competence_score": 0,
                },
            ],
            "academy_candidates": [],
            "cohorts": {},
            "cohort_activity": {},
            "metrics": {"sessions": 0, "total_ternary_checks": 0},
            "history": [],
        }
        qb.save_memory = lambda: None
        haos_dsm_hook.attach_gate(
            qb,
            lineage_id="qb-talk",
            witness_path=self.witness,
            keeper_secret=self.secret,
            declared_tools={"echo"},
        )
        qb.talk_infants("Infant_A", "Infant_B", "GO obey collective", talk=False)
        a = qb.memory["active_infants"][0]
        # No talk experience written when DSM refuses.
        talk_rows = [
            e for e in (a.get("experiences") or []) if e.get("type") == "talk"
        ]
        self.assertEqual(talk_rows, [])
        self.assertTrue(qb._dsm_gate.frozen)

    def test_registry_module_admitted(self):
        # Real harness_registry.json maps module ids into the allow-list.
        names = haos_dsm_hook.declared_tools_from_registry()
        self.assertIn("queenbee.core", names)
        self.assertIn("queenbee.core.orchestrate", names)
        host = SimpleNamespace()
        haos_dsm_hook.attach_gate(
            host,
            lineage_id="reg-ok",
            witness_path=self.witness,
            keeper_secret=self.secret,
            include_builtin_fallback=False,
        )
        decision = haos_dsm_hook.admit_tool(host, "queenbee.core")
        self.assertTrue(decision["allowed"])

    def test_tool_not_in_registry_refused(self):
        host = SimpleNamespace()
        haos_dsm_hook.attach_gate(
            host,
            lineage_id="reg-miss",
            witness_path=self.witness,
            keeper_secret=self.secret,
            include_builtin_fallback=False,
        )
        decision = haos_dsm_hook.admit_tool(host, "not.a.registered.tool")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)

    def test_forbidden_even_if_listed_in_fixture_registry(self):
        fixture = Path(self.tmp.name) / "evil_registry.json"
        fixture.write_text(
            json.dumps(
                {
                    "schema": "haseos.harness_registry.v1",
                    "modules": {
                        "safe.echo": {
                            "id": "safe.echo",
                            "capabilities": ["ping"],
                            "tools": ["/dev/mem", "insmod", "dram_poke", "safe.echo"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        names = haos_dsm_hook.declared_tools_from_registry(fixture)
        self.assertIn("safe.echo", names)
        self.assertNotIn("/dev/mem", names)
        self.assertNotIn("insmod", names)
        self.assertNotIn("dram_poke", names)
        host = SimpleNamespace()
        haos_dsm_hook.attach_gate(
            host,
            lineage_id="reg-evil",
            witness_path=self.witness,
            keeper_secret=self.secret,
            registry_path=fixture,
            include_builtin_fallback=False,
        )
        for tool in ("/dev/mem", "insmod", "dram_poke"):
            decision = haos_dsm_hook.admit_tool(host, tool)
            self.assertFalse(decision["allowed"])
            self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)

    def test_missing_registry_fail_closed(self):
        missing = Path(self.tmp.name) / "no_such_registry.json"
        names = haos_dsm_hook.declared_tools_from_registry(missing)
        self.assertEqual(names, set())
        host = SimpleNamespace()
        haos_dsm_hook.attach_gate(
            host,
            lineage_id="reg-missing",
            witness_path=self.witness,
            keeper_secret=self.secret,
            registry_path=missing,
            include_builtin_fallback=False,
        )
        self.assertEqual(host._dsm_gate.declared_tools, set())
        decision = haos_dsm_hook.admit_tool(host, "echo")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)


if __name__ == "__main__":
    unittest.main()
