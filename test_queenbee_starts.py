#!/usr/bin/env python3
"""D31 — QueenBee imports without torch / HRM guest."""

from __future__ import annotations

import sys
import unittest


class QueenBeeStartsWithoutTorchTests(unittest.TestCase):
    def test_import_queenbee_without_torch(self):
        sys.modules.pop("autoresearch_integration", None)
        import queenbee_integration as qb

        self.assertFalse(hasattr(qb, "HrmOrchestrator"))
        self.assertNotIn("autoresearch_integration", sys.modules)
        self.assertTrue(callable(qb._try_hrm_orchestrator))
        self.assertTrue(callable(qb.build_plain_infant))

    def test_spawn_plain_infant_when_hrm_missing(self):
        import queenbee_integration as qb

        infant = qb.build_plain_infant("observe localhost")
        self.assertEqual(infant["status"], "ACTIVE")
        self.assertEqual(infant["sandbox_tier"], "nursery")
        self.assertEqual(infant["experiences"], [])
        self.assertEqual(infant["competence_score"], 0)
        self.assertEqual(infant["task"], "observe localhost")
        self.assertTrue(str(infant["id"]).startswith("infant-plain-"))

    def test_queenbee_constructs_without_mouth(self):
        from queenbee_integration import QueenBee

        bee = QueenBee()
        self.assertTrue(hasattr(bee, "client"))
        self.assertTrue(bee.mouth_ok is False or bee.client is not None)


if __name__ == "__main__":
    unittest.main()
