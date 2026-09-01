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
from haos_dsm_cert import mint_haseos_cert


class DSMHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.witness = Path(self.tmp.name) / "witness.jsonl"
        self.secret = "test-keeper-secret-d2"
        self.lineage = "lineage-hook"

    def tearDown(self):
        self.tmp.cleanup()

    def _cert(self, lineage=None, tools=None):
        tool_set = set(tools or {"echo", "status"})
        return mint_haseos_cert(
            secret=self.secret,
            sovereign_id=lineage or self.lineage,
            role="lineage",
            slice_hosts=["localhost", "127.0.0.1"],
            slice_tools=sorted(tool_set),
            hours=24.0,
        )

    def _attach(self, host, *, lineage_id, declared_tools=None, **kwargs):
        tools = (
            set(declared_tools)
            if declared_tools is not None
            else kwargs.get("declared_tools")
        )
        if "cert" not in kwargs and "cert_path" not in kwargs:
            # Fresh witness dir per freeze-heavy tests; mint matching lineage cert.
            tool_names = tools
            if tool_names is None and kwargs.get("registry_path"):
                tool_names = haos_dsm_hook.declared_tools_from_registry(
                    kwargs["registry_path"]
                )
            elif tool_names is None and kwargs.get("include_builtin_fallback") is False:
                tool_names = haos_dsm_hook.declared_tools_from_registry()
            kwargs["cert"] = self._cert(
                lineage=lineage_id,
                tools=tool_names or {"echo", "status"},
            )
        if declared_tools is not None:
            kwargs["declared_tools"] = set(declared_tools)
        return haos_dsm_hook.attach_gate(
            host,
            lineage_id=lineage_id,
            witness_path=self.witness,
            keeper_secret=self.secret,
            **kwargs,
        )

    def _host(self, declared=None, **attach_kw):
        host = SimpleNamespace()
        tools = set(declared or {"echo", "status"})
        self._attach(host, lineage_id=self.lineage, declared_tools=tools, **attach_kw)
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
        self._attach(
            qb,
            lineage_id="qb-test",
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
        self._attach(
            qb,
            lineage_id="qb-talk",
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
        self._attach(
            host,
            lineage_id="reg-ok",
            include_builtin_fallback=False,
        )
        decision = haos_dsm_hook.admit_tool(host, "queenbee.core")
        self.assertTrue(decision["allowed"])

    def test_tool_not_in_registry_refused(self):
        host = SimpleNamespace()
        self._attach(
            host,
            lineage_id="reg-miss",
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
        self._attach(
            host,
            lineage_id="reg-evil",
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
        self._attach(
            host,
            lineage_id="reg-missing",
            registry_path=missing,
            include_builtin_fallback=False,
        )
        self.assertEqual(host._dsm_gate.declared_tools, set())
        decision = haos_dsm_hook.admit_tool(host, "echo")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)

    def test_nursery_named_capability_admitted_from_fixture(self):
        fixture = Path(self.tmp.name) / "nursery_registry.json"
        fixture.write_text(
            json.dumps(
                {
                    "schema": "haseos.harness_registry.v1",
                    "modules": {
                        "nursery.usb_state": {
                            "id": "nursery.usb_state",
                            "capabilities": ["mount", "serial.named"],
                            "tools": ["nursery.usb.mount"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        names = haos_dsm_hook.declared_tools_from_registry(fixture)
        self.assertIn("nursery.usb.mount", names)
        self.assertIn("nursery.usb_state.mount", names)
        host = SimpleNamespace()
        self._attach(
            host,
            lineage_id="emb-ok",
            registry_path=fixture,
            include_builtin_fallback=False,
        )
        decision = haos_dsm_hook.admit_tool(host, "nursery.usb.mount")
        self.assertTrue(decision["allowed"])

    def test_raw_tty_and_gpio_refused(self):
        fixture = Path(self.tmp.name) / "emb_registry.json"
        fixture.write_text(
            json.dumps(
                {
                    "schema": "haseos.harness_registry.v1",
                    "modules": {
                        "nursery.usb_state": {
                            "id": "nursery.usb_state",
                            "tools": ["nursery.usb.mount", "/dev/ttyUSB0", "/dev/gpiochip0"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        # Scrubbed from allow-list even if listed.
        names = haos_dsm_hook.declared_tools_from_registry(fixture)
        self.assertNotIn("/dev/ttyUSB0", names)
        self.assertNotIn("/dev/gpiochip0", names)
        host = SimpleNamespace()
        self._attach(
            host,
            lineage_id="emb-raw",
            registry_path=fixture,
            include_builtin_fallback=False,
        )
        for tool in ("/dev/ttyUSB0", "/dev/gpiochip0"):
            # Fresh gate each time (prior freeze sticks).
            self._attach(
                host,
                lineage_id="emb-raw",
                registry_path=fixture,
                include_builtin_fallback=False,
            )
            decision = haos_dsm_hook.admit_tool(host, tool)
            self.assertFalse(decision["allowed"])
            self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)

    def test_dev_mem_still_refused_if_listed(self):
        fixture = Path(self.tmp.name) / "mem_registry.json"
        fixture.write_text(
            json.dumps(
                {
                    "schema": "haseos.harness_registry.v1",
                    "modules": {
                        "evil": {"id": "evil", "tools": ["/dev/mem", "nursery.usb.mount"]}
                    },
                }
            ),
            encoding="utf-8",
        )
        host = SimpleNamespace()
        self._attach(
            host,
            lineage_id="emb-mem",
            registry_path=fixture,
            include_builtin_fallback=False,
        )
        decision = haos_dsm_hook.admit_tool(host, "/dev/mem")
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], REASON_SLICE_VIOLATION)


if __name__ == "__main__":
    unittest.main()
