from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from server.miscite.sources.http import backoff_sleep


@dataclass
class OpenRouterClient:
    api_key: str
    model: str
    timeout_seconds: float = 45.0

    def chat_json(self, *, system: str, user: str) -> dict:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json() or {}
                content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
                if not content:
                    raise RuntimeError("OpenRouter response missing message content")
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    cleaned = _strip_code_fence(content)
                    if cleaned != content:
                        try:
                            return json.loads(cleaned)
                        except json.JSONDecodeError as e:
                            snippet = content[:500].replace("\n", "\\n")
                            raise RuntimeError(f"Model did not return valid JSON. First 500 chars: {snippet}") from e
                    snippet = content[:500].replace("\n", "\\n")
                    raise RuntimeError(f"Model did not return valid JSON. First 500 chars: {snippet}")
            except requests.RequestException as e:
                last_err = e
                backoff_sleep(attempt)
        raise RuntimeError("OpenRouter request failed after retries") from last_err


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if not lines:
        return text
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
