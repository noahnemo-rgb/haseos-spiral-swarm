#!/usr/bin/env python3
"""D23 tests — git hook path/origin checks (fixtures only; no living secrets)."""

from __future__ import annotations

import unittest

from haos_dsm_githooks import (
    ALLOWED_ORIGIN,
    check_origin_url,
    check_staged_paths,
)


class GitHooksTests(unittest.TestCase):
    def test_staged_haseos_keeper_blocked(self):
        blocked = check_staged_paths([".haseos_keeper"])
        self.assertEqual(blocked, [".haseos_keeper"])

    def test_staged_dsm_cert_queenbee_blocked(self):
        blocked = check_staged_paths(["dsm_cert_queenbee.json"])
        self.assertEqual(blocked, ["dsm_cert_queenbee.json"])

    def test_staged_runbook_allowed(self):
        blocked = check_staged_paths(["docs/HASEOS_DSM_HITL_RUNBOOK.md"])
        self.assertEqual(blocked, [])

    def test_origin_with_pat_userinfo_blocked(self):
        url = (
            "https://user:ghp_fixture-not-a-real-token"
            "@github.com/noahnemo-rgb/haseos-spiral-swarm.git"
        )
        self.assertFalse(check_origin_url(url))
        self.assertNotEqual(url, ALLOWED_ORIGIN)

    def test_exact_allowed_origin_ok(self):
        self.assertTrue(check_origin_url(ALLOWED_ORIGIN))
        self.assertEqual(
            ALLOWED_ORIGIN,
            "https://github.com/noahnemo-rgb/haseos-spiral-swarm.git",
        )

    def test_staged_vendored_trees_blocked(self):
        blocked = check_staged_paths(["hrm/foo", "autoresearch/bar"])
        self.assertEqual(blocked, ["hrm/foo", "autoresearch/bar"])


if __name__ == "__main__":
    unittest.main()
