from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def get_prompt(name: str) -> str:
    filename = name if name.endswith(".txt") else f"{name}.txt"
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, **values: object) -> str:
    raw = get_prompt(name)
    if not values:
        return raw
    normalized = {key: "" if value is None else str(value) for key, value in values.items()}
    try:
        return Template(raw).substitute(normalized)
    except KeyError as exc:
        missing = exc.args[0]
        raise KeyError(f"Missing prompt variable '{missing}' for prompt '{name}'.") from exc
