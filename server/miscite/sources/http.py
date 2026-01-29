from __future__ import annotations

import time
from dataclasses import dataclass

import requests


@dataclass
class HttpClient:
    timeout_seconds: float = 20.0

    def get_json(self, url: str, *, headers: dict[str, str] | None = None, params: dict | None = None):
        resp = requests.get(url, headers=headers, params=params, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def post_json(self, url: str, *, headers: dict[str, str] | None = None, json_body: dict | None = None):
        resp = requests.post(url, headers=headers, json=json_body, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()


def backoff_sleep(attempt: int) -> None:
    # basic exponential backoff with cap
    time.sleep(min(8.0, 0.5 * (2**attempt)))

