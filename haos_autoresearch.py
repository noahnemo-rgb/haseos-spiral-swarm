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
KERNEL_SCHEMA = "haseos.ethical_kernel.v1"
MUTABLE_SURFACE = "task"
REASON_JUDGE_MISSING = "JUDGE_MISSING"
DEFAULT_BUDGET_CHARS = 400


def judge_is_present() -> bool:
    """True only when DSM imports and ethical_kernel schema is present."""
    try:
        import haos_dsm  # noqa: F401
        import spiral_harness

        kernel = spiral_harness.ethical_kernel()
    except Exception:
        return False
    return isinstance(kernel, dict) and kernel.get("schema") == KERNEL_SCHEMA


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
    judge_available: bool | None = None,
) -> dict[str, Any]:
    """Refuse, keep, or discard. Writes trials only on keep/discard.

    ``judge_available is None`` uses ``judge_is_present()``.
    Explicit True/False remains a test override.
    """
    present = judge_is_present() if judge_available is None else bool(judge_available)
    judged = judge_trial(hypothesis, present)
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
    append_candidate_experience(infant, trial, outcome)
    return {"status": outcome, "trial": trial}


def append_candidate_experience(infant: dict, trial: dict, status: str) -> dict[str, Any]:
    """Candidate experience on keep/discard. Promotion stays HITL."""
    infant.setdefault("experiences", [])
    outcome = "keep" if status == "keep" else "discard"
    delta = 1 if outcome == "keep" else 0
    row = {
        "type": "autoresearch",
        "source": "/autoresearch",
        "outcome": outcome,
        "summary": f"autoresearch {outcome}",
        "task": infant.get("task"),
        "related": {"trial_id": trial.get("id")},
        "competence_delta": delta,
        "timestamp": _utc_now(),
    }
    infant["experiences"].append(row)
    if outcome == "keep":
        infant["competence_score"] = int(infant.get("competence_score") or 0) + 1
    return row


def already_logged_trial(infant: dict | None, trial_id: str | None) -> bool:
    """True iff an experience row already records this trial_id (skip second append)."""
    if not trial_id or not isinstance(infant, dict):
        return False
    for row in infant.get("experiences") or []:
        if not isinstance(row, dict):
            continue
        related = row.get("related")
        if isinstance(related, dict) and related.get("trial_id") == trial_id:
            return True
    return False


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


def restore_kept_surface(infant: dict) -> dict[str, Any] | None:
    """Put a kept hypothesis back on infant[\"task\"]. No new trial. Discard is a no-op."""
    ctx = last_trial_context(infant)
    if ctx and ctx.get("outcome") == "keep" and ctx.get("hypothesis"):
        infant["task"] = ctx["hypothesis"]
        return ctx
    return None


def _format_trial_fields(row: dict[str, Any], *, label: str) -> str:
    return (
        f"{label}: "
        f"id={row.get('trial_id')} "
        f"outcome={row.get('outcome')} "
        f"reason={row.get('reason')} "
        f"hypothesis={row.get('hypothesis')} "
        f"mutable_surface={row.get('mutable_surface')}"
    )


def format_autoresearch_status(infant: dict | None) -> str:
    """Inspect-only last trial + cycle baseline. Never runs apply_trial."""
    present = "true" if judge_is_present() else "false"
    lines = [
        f"judge: presence of DSM + ethical_kernel.v1 ({present})",
    ]
    if isinstance(infant, dict) and infant.get("id"):
        lines.insert(0, f"infant: {infant.get('id')}")
    ctx = last_trial_context(infant)
    if ctx is None:
        lines.append("last trial: no prior trial")
    else:
        lines.append(_format_trial_fields(ctx, label="last trial"))
    baseline = infant.get("last_cycle_baseline") if isinstance(infant, dict) else None
    if isinstance(baseline, dict) and baseline:
        lines.append(_format_trial_fields(baseline, label="cycle baseline"))
    return "\n".join(lines)
