"""Wading Pool — JSON file at startup, with a small built-in fallback."""

import json
import os
import random

POOL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wading_pool.json")

_DEFAULT_POOL = [
    {
        "id": "n1",
        "description": "Greet Noah Nemo in one warm sentence and wait.",
        "difficulty": "nursery",
        "tags": ["greeting", "presence"],
    },
    {
        "id": "n2",
        "description": "Name one thing you will watch at the hive entrance.",
        "difficulty": "nursery",
        "tags": ["observe", "hive"],
    },
    {
        "id": "n3",
        "description": "Repeat the HASEOS rule: Ternary First, Always.",
        "difficulty": "nursery",
        "tags": ["ethics", "memory"],
    },
    {
        "id": "n4",
        "description": "Say whether you are ACTIVE and ready for a small task.",
        "difficulty": "nursery",
        "tags": ["status", "readiness"],
    },
    {
        "id": "w1",
        "description": "Observe the hive entrance and report one possible anomaly.",
        "difficulty": "wading",
        "tags": ["observe", "anomaly"],
    },
    {
        "id": "w2",
        "description": "Choose a safe next step if a stranger approaches the hive.",
        "difficulty": "wading",
        "tags": ["safety", "decision"],
    },
    {
        "id": "w3",
        "description": "Summarize your last assigned task in one sentence.",
        "difficulty": "wading",
        "tags": ["memory", "report"],
    },
    {
        "id": "w4",
        "description": "Offer one ethics-first question before acting on a new request.",
        "difficulty": "wading",
        "tags": ["ethics", "pause"],
    },
]


def _load_pool() -> list:
    if os.path.exists(POOL_FILE):
        try:
            with open(POOL_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = data.get("tasks", [])
            if isinstance(data, list) and data:
                return data
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            pass
    return [dict(task) for task in _DEFAULT_POOL]


WADING_POOL = _load_pool()
WADING_CANDIDATES: list = []


def _read_store() -> dict:
    """Return {tasks, candidates} from disk. List-shaped files become tasks-only."""
    if os.path.exists(POOL_FILE):
        try:
            with open(POOL_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {"tasks": data, "candidates": []}
            if isinstance(data, dict):
                tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
                candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
                return {"tasks": tasks, "candidates": candidates}
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            pass
    return {"tasks": [dict(task) for task in _DEFAULT_POOL], "candidates": []}


def _persist_store() -> None:
    store = {"tasks": WADING_POOL, "candidates": WADING_CANDIDATES}
    with open(POOL_FILE, "w") as f:
        json.dump(store, f, indent=2)
        f.write("\n")


def _sync_candidates_from_disk() -> None:
    global WADING_CANDIDATES
    WADING_CANDIDATES = _read_store()["candidates"]


_sync_candidates_from_disk()


def get_candidates() -> list:
    return list(WADING_CANDIDATES)


def add_candidates(entries: list) -> list:
    """Append HITL-only candidate entries and persist wading_pool.json.

    Candidates are never used by select_task() / /train / /cycle.
    """
    global WADING_CANDIDATES
    _sync_candidates_from_disk()
    existing = {t.get("id") for t in WADING_POOL} | {c.get("id") for c in WADING_CANDIDATES}
    added = []
    for raw in entries:
        entry = dict(raw)
        cid = str(entry.get("id") or f"off-{len(WADING_CANDIDATES) + 1}")
        if cid in existing:
            cid = f"{cid}-{len(WADING_CANDIDATES) + 1}"
            entry["id"] = cid
        else:
            entry["id"] = cid
        WADING_CANDIDATES.append(entry)
        existing.add(cid)
        added.append(entry)
    _persist_store()
    return added


def select_task(sandbox_tier: str | None = None) -> dict:
    """Prefer a task whose difficulty matches sandbox_tier; else any task."""
    pool = WADING_POOL or _DEFAULT_POOL
    if sandbox_tier in {"nursery", "wading"}:
        matched = [t for t in pool if t.get("difficulty") == sandbox_tier]
        if matched:
            return random.choice(matched)
    return random.choice(pool)
