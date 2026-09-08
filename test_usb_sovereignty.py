#!/usr/bin/env python3
"""D35 tests — USB snapshot seals Memory Sovereignty fields (no QueenBee, no torch)."""

from __future__ import annotations

import unittest

import usb_state


class UsbSovereigntyTests(unittest.TestCase):
    def test_seal_copies_keep_trial_and_family_id(self):
        infant = {
            "id": "parent-1",
            "task": "observe localhost",
            "experiences": [{"text": "saw loopback"}],
            "autoresearch_trials": [
                {"id": "t-keep-1", "outcome": "keep", "hypothesis": "stay local"},
            ],
            "last_cycle_baseline": {"outcome": "keep", "trial_id": "t-keep-1"},
            "family_id": "house-a",
            "parent_id": None,
            "family_role": "parent",
            "competence_score": 2,
        }
        sealed = usb_state.seal_sovereignty(infant)
        self.assertEqual(sealed["family_id"], "house-a")
        self.assertEqual(sealed["family_role"], "parent")
        self.assertEqual(sealed["autoresearch_trials"][0]["outcome"], "keep")
        self.assertEqual(sealed["task"], "observe localhost")
        sealed["autoresearch_trials"].append({"id": "invented"})
        sealed["experiences"].append({"text": "invented"})
        self.assertEqual(len(infant["autoresearch_trials"]), 1)
        self.assertEqual(len(infant["experiences"]), 1)

    def test_seal_does_not_invent_trials_on_bare_infant(self):
        bare = {"id": "infant-plain", "task": "observe localhost", "status": "ACTIVE"}
        sealed = usb_state.seal_sovereignty(bare)
        self.assertNotIn("autoresearch_trials", sealed)
        self.assertNotIn("family_id", sealed)
        self.assertNotIn("parent_id", sealed)
        self.assertNotIn("family_role", sealed)
        self.assertEqual(sealed["task"], "observe localhost")

    def test_memory_card_after_keep_shows_trial_and_family(self):
        infant = {
            "id": "child-1",
            "task": "observe localhost",
            "family_id": "house-a",
            "autoresearch_trials": [
                {"id": "t-keep-1", "outcome": "keep", "hypothesis": "stay local"},
            ],
        }
        card = usb_state.infant_memory_card(infant)
        self.assertEqual(card["trial_count"], 1)
        self.assertEqual(card["last_trial_outcome"], "keep")
        self.assertEqual(card["family_id"], "house-a")

    def test_create_empty_airgap_enforced_true(self):
        state = usb_state.create_empty("node-a")
        self.assertIs(state["airgap_enforced"], True)


if __name__ == "__main__":
    unittest.main()
