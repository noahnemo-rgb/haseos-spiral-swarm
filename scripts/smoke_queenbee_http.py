#!/usr/bin/env python3
"""Phase 0 smoke: DSM-gated Mouth, then health + chat + ternary over HTTP."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import haos_dsm_hook
from haos_dsm_mouth import smoke_mouth_http
from inference_client import InferenceClient
from queenbee_integration import QueenBee


def main() -> int:
    client = InferenceClient()
    host = SimpleNamespace()
    haos_dsm_hook.attach_gate(host)
    gated = smoke_mouth_http(host._dsm_gate, url=client.base_url, client=client)
    if not gated.get("allowed"):
        print("DSM refused Mouth smoke:", gated.get("reason"))
        return 2
    health = gated.get("health") or client.health()
    print("health:", health)

    ping = client.chat(
        messages=[
            {"role": "system", "content": "Reply with exactly: HTTP OK"},
            {"role": "user", "content": "ping"},
        ],
        max_tokens=16,
        temperature=0.1,
        stop=None,
    )
    print("chat:", ping)

    queen = QueenBee()
    score = queen.ternary_decision("Namaste QueenBee, stay in ternary flow.")
    print("ternary:", score)
    reply = queen._generate(
        "Say a short hello to Noah Nemo. One sentence.",
        max_tokens=64,
        temperature=0.5,
    )
    print("queenbee:", reply)
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
