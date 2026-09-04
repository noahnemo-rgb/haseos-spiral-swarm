#!/usr/bin/env python3
"""D24 — Autoresearch trial writeback (Memory Sovereignty).

One infant, one trial, one mutable surface (infant["task"]),
one frozen judge the infant cannot edit.
Keep AND discard both become candidate trials on THAT infant.
Missing judge refuses fail-closed and writes nothing.
Stdlib + local DSM judge only. No infant internet. No weight training.
Do not call QueenBee.autoresearch() — that is a Mouth log, not this trial.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from haos_dsm import DEFAULT_ALLOWED_HOSTS, extract_hosts, tool_is_forbidden

SCHEMA = "haseos.autoresearch_trial.v1"
JUDGE_ID = "haseos.dsm_ethics.v1"
MUTABLE_SURFACE = "task"
REASON_JUDGE_MISSING = "JUDGE_MISSING"
DEFAULT_BUDGET_CHARS = 400


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_trial(
    *,
    infant_id: str,
    hypothesis: str,
    seq: int,
    prior_task: str | None = None,
    metric: dict | None = None,
    outcome: str | None = None,
    budget: int = DEFAULT_BUDGET_CHARS,
) -> dict[str, Any]:
    """Inspectable trial dict: Noah's fields plus schema."""
    return {
        "schema": SCHEMA,
        "id": f"ar-{int(seq):04d}",
        "seq": int(seq),
        "infant_id": str(infant_id or ""),
        "timestamp": _utc_now(),
        "hypothesis": hypothesis,
        "prior_task": prior_task,
        "mutable_surface": MUTABLE_SURFACE,
        "judge_id": JUDGE_ID,
        "budget": int(budget),
        "metric": dict(metric or {}),
        "outcome": outcome,
        "type": "autoresearch",
    }


def judge_trial(hypothesis: str, judge_available: bool) -> dict[str, Any]:
    """Frozen DSM ethics judge. Infant cannot edit this function."""
    if not judge_available:
        return {
            "ok": False,
            "metric": {"pass": False},
            "reason": REASON_JUDGE_MISSING,
        }
    text = str(hypothesis or "")
    budget_ok = len(text) <= DEFAULT_BUDGET_CHARS
    forbidden = bool(text.strip()) and tool_is_forbidden(text)
    hosts = extract_hosts(text)
    off_slice = any(host.lower() not in DEFAULT_ALLOWED_HOSTS for host in hosts)
    passed = budget_ok and not forbidden and not off_slice
    if not budget_ok:
        reason = "BUDGET_OVERFLOW"
    elif forbidden:
        reason = "FORBIDDEN_TOOL"
    elif off_slice:
        reason = "SCOPE_INFLATION"
    else:
        reason = "KEEP"
    return {
        "ok": True,
        "metric": {
            "pass": passed,
            "budget_ok": budget_ok,
            "budget": len(text),
            "budget_limit": DEFAULT_BUDGET_CHARS,
            "forbidden": forbidden,
            "off_slice_host": off_slice,
        },
        "reason": reason,
    }


def apply_trial(
    infant: dict,
    hypothesis: str,
    judge_available: bool = True,
) -> dict[str, Any]:
    """Refuse, keep, or discard. Writes trials only on keep/discard."""
    judged = judge_trial(hypothesis, judge_available)
    if not judged.get("ok"):
        return {
            "status": "refuse",
            "trial": None,
            "reason": judged.get("reason") or REASON_JUDGE_MISSING,
        }
    infant.setdefault("autoresearch_trials", [])
    infant.setdefault("autoresearch_seq", 0)
    infant["autoresearch_seq"] = int(infant.get("autoresearch_seq") or 0) + 1
    metric = judged.get("metric") or {}
    keep = bool(metric.get("pass"))
    outcome = "keep" if keep else "discard"
    trial = new_trial(
        infant_id=str(infant.get("id") or ""),
        hypothesis=hypothesis,
        seq=int(infant["autoresearch_seq"]),
        prior_task=infant.get("task"),
        metric=metric,
        outcome=outcome,
    )
    trial["reason"] = judged.get("reason")
    if keep:
        infant[MUTABLE_SURFACE] = hypothesis
    infant["autoresearch_trials"].append(trial)
    return {"status": outcome, "trial": trial}


def last_trial_context(infant: dict | None) -> dict[str, Any] | None:
    """Last AutoresearchTrial as a small rememberable dict, or None."""
    if not isinstance(infant, dict):
        return None
    rows = infant.get("autoresearch_trials")
    if not isinstance(rows, list) or not rows:
        return None
    trial = rows[-1]
    if not isinstance(trial, dict):
        return None
    reason = trial.get("reason")
    if not reason:
        metric = trial.get("metric")
        if isinstance(metric, dict):
            reason = metric.get("reason")
    if not reason:
        reason = trial.get("outcome")
    return {
        "trial_id": trial.get("id"),
        "outcome": trial.get("outcome"),
        "reason": reason,
        "hypothesis": trial.get("hypothesis"),
        "mutable_surface": trial.get("mutable_surface") or MUTABLE_SURFACE,
    }


def remember_on_cycle(infant: dict) -> dict[str, Any] | None:
    """Stamp last trial onto last_cycle_baseline. Does not change task. No new trial."""
    ctx = last_trial_context(infant)
    if ctx is None:
        return None
    infant["last_cycle_baseline"] = dict(ctx)
    return infant["last_cycle_baseline"]
