#!/usr/bin/env python3
"""OpenAI-compatible HTTP client for QueenBee (llama-server)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / "bonsai.env"

DEFAULT_STOP = [
    "\n\n",
    "System:",
    "Instruction:",
    "QueenBee:",
    "Respond as",
    "Use the tone",
    "Don't repeat",
    "Always be in",
    "Ternary alignment confirmed",
]


def load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


class InferenceError(RuntimeError):
    pass


class InferenceClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 300.0,
    ):
        self.base_url = (base_url or os.environ.get("QUEENBEE_BASE_URL", "http://127.0.0.1:8080")).rstrip("/")
        self.model = model or os.environ.get("QUEENBEE_MODEL", "qwen2.5-1.5b")
        self.timeout = timeout

    def health(self) -> dict:
        for path in ("/health", "/v1/health"):
            try:
                return self._get(path)
            except InferenceError:
                continue
        raise InferenceError(
            f"llama-server is not reachable at {self.base_url}. "
            "Start it with: bash scripts/serve_local.sh"
        )

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.6,
        top_p: float = 0.95,
        top_k: int = 90,
        repeat_penalty: float = 2.5,
        stop: Optional[Iterable[str]] = DEFAULT_STOP,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
            "stream": False,
        }
        if stop:
            payload["stop"] = list(stop)
        data = self._post("/v1/chat/completions", payload)
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise InferenceError(f"Unexpected chat response: {data!r}") from exc

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        return self._request(req)

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        return self._request(req)

    def _request(self, req: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise InferenceError(f"HTTP {exc.code} from {req.full_url}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise InferenceError(
                f"Cannot reach {req.full_url}: {exc.reason}. "
                "Start the server with: bash scripts/serve_local.sh"
            ) from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
