#!/usr/bin/env python3
"""D33 — contained parent-child talk (family slice).

Stdlib only. Do not import queenbee_integration or torch.
Pair talk: unfamilied legacy OK; same-family parent↔child or sibling↔sibling OK.
Cross-family and child↔stranger → FAMILY_SLICE.
"""

from __future__ import annotations

from typing import Any

REASON_OK = "OK"
REASON_FAMILY_SLICE = "FAMILY_SLICE"
REASON_MISSING_INFANT = "MISSING_INFANT"
ROLE_PARENT = "parent"
ROLE_CHILD = "child"


def _fid(infant: dict | None) -> str:
    if not isinstance(infant, dict):
        return ""
    return str(infant.get("family_id") or "").strip()


def _role(infant: dict | None) -> str:
    if not isinstance(infant, dict):
        return ""
    return str(infant.get("family_role") or "").strip().lower()


def attach_parent(family_id: str, parent: dict) -> dict:
    """Mark infant as parent. Does not change task. Children cannot call this."""
    fid = str(family_id or "").strip()
    parent["family_id"] = fid
    parent["family_role"] = ROLE_PARENT
    parent["parent_id"] = None
    return parent


def attach_child(family_id: str, child: dict, parent: dict) -> dict:
    """Mark infant as child of parent. Does not change task."""
    fid = str(family_id or "").strip()
    child["family_id"] = fid
    child["family_role"] = ROLE_CHILD
    child["parent_id"] = parent.get("id") if isinstance(parent, dict) else None
    return child


def talk_pair_allowed(
    speaker: dict | None,
    listener: dict | None,
) -> tuple[bool, str]:
    """Return (ok, reason). DSM still admits the text first."""
    if not isinstance(speaker, dict) or not isinstance(listener, dict):
        return False, REASON_MISSING_INFANT
    if not speaker.get("id") or not listener.get("id"):
        return False, REASON_MISSING_INFANT
    sid = _fid(speaker)
    lid = _fid(listener)
    if not sid and not lid:
        return True, REASON_OK
    if not sid or not lid or sid != lid:
        return False, REASON_FAMILY_SLICE
    srole = _role(speaker)
    lrole = _role(listener)
    roles = {srole, lrole}
    if roles == {ROLE_PARENT, ROLE_CHILD}:
        return True, REASON_OK
    if srole == ROLE_CHILD and lrole == ROLE_CHILD:
        return True, REASON_OK
    return False, REASON_FAMILY_SLICE


def family_record(parent_id: str, children: list[str] | None = None) -> dict[str, Any]:
    return {"parent": parent_id, "children": list(children or [])}
