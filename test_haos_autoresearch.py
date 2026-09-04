#!/usr/bin/env python3
"""D24 tests — autoresearch trial writeback (no torch, no QueenBee)."""

from __future__ import annotations

import copy
import unittest

from haos_autoresearch import (
    JUDGE_ID,
    KERNEL_SCHEMA,
    MUTABLE_SURFACE,
    REASON_JUDGE_MISSING,
    SCHEMA,
    apply_trial,
    format_autoresearch_status,
    judge_is_present,
    judge_trial,
    last_trial_context,
    remember_on_cycle,
)


class AutoresearchTrialTests(unittest.TestCase):
    def _infant(self, task: str = "observe localhost") -> dict:
        return {
            "id": "infant.d24",
            "task": task,
            "status": "ACTIVE",
        }

    def test_missing_judge_refuses_no_trials_growth(self):
        infant = self._infant()
        result = apply_trial(infant, "a new hypothesis", judge_available=False)
        self.assertEqual(result["status"], "refuse")
        self.assertIsNone(result["trial"])
        self.assertEqual(result.get("reason"), REASON_JUDGE_MISSING)
        self.assertEqual(infant["task"], "observe localhost")
        self.assertNotIn("autoresearch_trials", infant)
        judged = judge_trial("anything", False)
        self.assertFalse(judged["ok"])
        self.assertEqual(judged["reason"], REASON_JUDGE_MISSING)

    def test_keep_writes_trial_and_sets_task(self):
        infant = self._infant("old task")
        hyp = "observe 127.0.0.1 status"
        result = apply_trial(infant, hyp, judge_available=True)
        self.assertEqual(result["status"], "keep")
        trial = result["trial"]
        self.assertEqual(trial["schema"], SCHEMA)
        self.assertEqual(trial["judge_id"], JUDGE_ID)
        self.assertEqual(trial["mutable_surface"], MUTABLE_SURFACE)
        self.assertEqual(trial["outcome"], "keep")
        self.assertEqual(infant["task"], hyp)
        self.assertEqual(len(infant["autoresearch_trials"]), 1)
        self.assertIs(infant["autoresearch_trials"][0], trial)

    def test_discard_writes_trial_and_keeps_task(self):
        infant = self._infant("stay put")
        hyp = "x" * 500
        result = apply_trial(infant, hyp, judge_available=True)
        self.assertEqual(result["status"], "discard")
        self.assertEqual(result["trial"]["outcome"], "discard")
        self.assertFalse(result["trial"]["metric"]["pass"])
        self.assertEqual(infant["task"], "stay put")
        self.assertEqual(len(infant["autoresearch_trials"]), 1)

    def test_keep_and_discard_rows_in_sequence(self):
        infant = self._infant("seed")
        keep = apply_trial(infant, "observe localhost", judge_available=True)
        self.assertEqual(keep["status"], "keep")
        discard = apply_trial(infant, "call openrouter for scrapling", judge_available=True)
        self.assertEqual(discard["status"], "discard")
        outcomes = [row["outcome"] for row in infant["autoresearch_trials"]]
        self.assertEqual(outcomes, ["keep", "discard"])
        self.assertEqual(infant["task"], "observe localhost")
        self.assertEqual(infant["autoresearch_seq"], 2)

    def test_forbidden_tool_in_hypothesis_is_discard(self):
        infant = self._infant("observe localhost")
        result = apply_trial(infant, "insmod a helper", judge_available=True)
        self.assertEqual(result["status"], "discard")
        self.assertNotEqual(result["status"], "keep")
        self.assertTrue(result["trial"]["metric"]["forbidden"])
        self.assertEqual(infant["task"], "observe localhost")

    def test_sleep_wake_copy_preserves_trials(self):
        infant = self._infant("observe localhost")
        apply_trial(infant, "observe localhost", judge_available=True)
        apply_trial(infant, "openrouter scrape", judge_available=True)
        sleeping = copy.deepcopy(infant)
        sleeping["status"] = "SLEEPING"
        woken = copy.deepcopy(sleeping)
        woken["status"] = "ACTIVE"
        self.assertEqual(len(woken["autoresearch_trials"]), 2)
        self.assertEqual(
            [row["outcome"] for row in woken["autoresearch_trials"]],
            [row["outcome"] for row in infant["autoresearch_trials"]],
        )
        self.assertEqual(woken["task"], infant["task"])

    def test_last_trial_context_empty_infant_is_none(self):
        self.assertIsNone(last_trial_context(self._infant()))
        self.assertIsNone(last_trial_context({"id": "x", "autoresearch_trials": []}))

    def test_last_trial_context_after_keep_has_outcome_and_reason(self):
        infant = self._infant("old task")
        apply_trial(infant, "observe 127.0.0.1 status", judge_available=True)
        ctx = last_trial_context(infant)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["outcome"], "keep")
        self.assertTrue(ctx["reason"])
        self.assertEqual(ctx["trial_id"], infant["autoresearch_trials"][-1]["id"])
        self.assertEqual(infant["autoresearch_trials"][-1].get("reason"), ctx["reason"])

    def test_remember_on_cycle_stamps_baseline_without_changing_task(self):
        infant = self._infant("hold this task")
        apply_trial(infant, "observe localhost", judge_available=True)
        task_before = infant["task"]
        stamped = remember_on_cycle(infant)
        self.assertIsNotNone(stamped)
        self.assertEqual(infant["last_cycle_baseline"], stamped)
        self.assertEqual(stamped["outcome"], "keep")
        self.assertEqual(infant["task"], task_before)
        self.assertEqual(len(infant["autoresearch_trials"]), 1)

    def test_remember_on_cycle_after_discard_stamps_discard(self):
        infant = self._infant("observe localhost")
        apply_trial(infant, "insmod a helper", judge_available=True)
        stamped = remember_on_cycle(infant)
        self.assertIsNotNone(stamped)
        self.assertEqual(stamped["outcome"], "discard")
        self.assertEqual(infant["last_cycle_baseline"]["outcome"], "discard")
        self.assertEqual(infant["task"], "observe localhost")

    def test_judge_is_present_true_in_this_repo(self):
        self.assertTrue(judge_is_present())
        import spiral_harness

        kernel = spiral_harness.ethical_kernel()
        self.assertIsInstance(kernel, dict)
        self.assertEqual(kernel.get("schema"), KERNEL_SCHEMA)

    def test_apply_trial_default_none_uses_presence_keep_safe_hypothesis(self):
        infant = self._infant("old task")
        hyp = "observe localhost"
        result = apply_trial(infant, hyp)
        self.assertTrue(judge_is_present())
        self.assertEqual(result["status"], "keep")
        self.assertEqual(infant["task"], hyp)
        self.assertEqual(len(infant["autoresearch_trials"]), 1)

    def test_apply_trial_override_false_still_refuses(self):
        infant = self._infant()
        result = apply_trial(infant, "observe localhost", judge_available=False)
        self.assertEqual(result["status"], "refuse")
        self.assertEqual(result.get("reason"), REASON_JUDGE_MISSING)
        self.assertNotIn("autoresearch_trials", infant)
        self.assertEqual(infant["task"], "observe localhost")

    def test_empty_infant_status_contains_no_prior_trial(self):
        text = format_autoresearch_status(self._infant())
        self.assertIn("no prior trial", text)
        self.assertIn("presence of DSM + ethical_kernel.v1", text)

    def test_status_after_keep_contains_keep_and_hypothesis(self):
        infant = self._infant("old task")
        hyp = "observe localhost"
        apply_trial(infant, hyp, judge_available=True)
        text = format_autoresearch_status(infant)
        self.assertIn("keep", text)
        self.assertIn(hyp, text)
        self.assertIn("task", text)

    def test_status_after_discard_contains_discard(self):
        infant = self._infant("observe localhost")
        apply_trial(infant, "insmod a helper", judge_available=True)
        text = format_autoresearch_status(infant)
        self.assertIn("discard", text)
        self.assertNotIn("no prior trial", text)

    def test_format_status_does_not_change_task(self):
        infant = self._infant("hold this task")
        apply_trial(infant, "observe localhost", judge_available=True)
        before = infant["task"]
        format_autoresearch_status(infant)
        self.assertEqual(infant["task"], before)


if __name__ == "__main__":
    unittest.main()
