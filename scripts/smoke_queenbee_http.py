#!/usr/bin/env python3
"""Phase 0 smoke: health + one chat turn + one ternary check over HTTP."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inference_client import InferenceClient
from queenbee_integration import QueenBee


def main() -> int:
    client = InferenceClient()
    health = client.health()
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
