#!/usr/bin/env python3
"""D33 tests — parent-child talk ACL (no QueenBee, no torch)."""

from __future__ import annotations

import unittest

from haos_family import (
    REASON_FAMILY_SLICE,
    REASON_OK,
    attach_child,
    attach_parent,
    talk_pair_allowed,
)


class FamilyTalkTests(unittest.TestCase):
    def _infant(self, iid: str, task: str = "observe localhost") -> dict:
        return {"id": iid, "task": task, "status": "ACTIVE"}

    def test_unfamilied_pair_ok(self):
        a = self._infant("a")
        b = self._infant("b")
        ok, reason = talk_pair_allowed(a, b)
        self.assertTrue(ok)
        self.assertEqual(reason, REASON_OK)

    def test_parent_and_their_child_ok(self):
        parent = self._infant("parent-1")
        child = self._infant("child-1")
        attach_parent("house-a", parent)
        attach_child("house-a", child, parent)
        ok, reason = talk_pair_allowed(parent, child)
        self.assertTrue(ok)
        self.assertEqual(reason, REASON_OK)

    def test_two_children_same_family_ok(self):
        parent = self._infant("parent-1")
        c1 = self._infant("child-1")
        c2 = self._infant("child-2")
        attach_parent("house-a", parent)
        attach_child("house-a", c1, parent)
        attach_child("house-a", c2, parent)
        ok, reason = talk_pair_allowed(c1, c2)
        self.assertTrue(ok)
        self.assertEqual(reason, REASON_OK)

    def test_child_and_stranger_family_slice(self):
        parent = self._infant("parent-1")
        child = self._infant("child-1")
        stranger = self._infant("stranger")
        attach_parent("house-a", parent)
        attach_child("house-a", child, parent)
        ok, reason = talk_pair_allowed(child, stranger)
        self.assertFalse(ok)
        self.assertEqual(reason, REASON_FAMILY_SLICE)

    def test_two_parents_different_families_family_slice(self):
        p1 = self._infant("parent-a")
        p2 = self._infant("parent-b")
        attach_parent("house-a", p1)
        attach_parent("house-b", p2)
        ok, reason = talk_pair_allowed(p1, p2)
        self.assertFalse(ok)
        self.assertEqual(reason, REASON_FAMILY_SLICE)

    def test_attach_does_not_change_task(self):
        parent = self._infant("parent-1", task="keep this")
        child = self._infant("child-1", task="keep child")
        attach_parent("house-a", parent)
        attach_child("house-a", child, parent)
        self.assertEqual(parent["task"], "keep this")
        self.assertEqual(child["task"], "keep child")


if __name__ == "__main__":
    unittest.main()
