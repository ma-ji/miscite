from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import json_repair
import requests

from server.miscite.cache import Cache
from server.miscite.sources.http import backoff_sleep


@dataclass
class OpenRouterClient:
    api_key: str
    model: str
    timeout_seconds: float = 45.0
    cache: Cache | None = None

    def chat_json(self, *, system: str, user: str) -> dict:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required")

        cache = self.cache
        cache_ttl_days = cache.settings.cache_llm_ttl_days if cache and cache.settings.cache_enabled else 0
        if cache and cache_ttl_days > 0:
            system_h = hashlib.sha256(system.encode("utf-8")).hexdigest()
            user_h = hashlib.sha256(user.encode("utf-8")).hexdigest()
            hit, cached = cache.get_json("openrouter.chat_json", [self.model, "temp:0.2", system_h, user_h])
            if hit and isinstance(cached, dict):
                return cached

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
                content = _extract_message_content(data)
                if not content:
                    err = (data.get("error") or {}).get("message")
                    if err:
                        raise RuntimeError(f"OpenRouter error response: {err}")
                    snippet = json.dumps(data, ensure_ascii=True)[:1000]
                    raise RuntimeError(f"OpenRouter response missing message content. First 1000 chars: {snippet}")
                try:
                    payload = _load_json_payload(content)
                    if cache and cache_ttl_days > 0:
                        cache.set_json(
                            "openrouter.chat_json",
                            [self.model, "temp:0.2", system_h, user_h],
                            payload,
                            ttl_seconds=float(cache_ttl_days) * 86400.0,
                        )
                    return payload
                except json.JSONDecodeError as e:
                    snippet = content[:500].replace("\n", "\\n")
                    raise RuntimeError(f"Model did not return valid JSON. First 500 chars: {snippet}") from e
            except requests.RequestException as e:
                last_err = e
                backoff_sleep(attempt)
        raise RuntimeError("OpenRouter request failed after retries") from last_err


def _extract_message_content(data: dict) -> str | None:
    choices = data.get("choices") or []
    if not choices:
        return None

    choice = choices[0] or {}
    message = choice.get("message")
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            text = content.get("text") or content.get("content")
            if isinstance(text, str):
                return text
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                    continue
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str) and text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)
        output_text = message.get("output_text")
        if isinstance(output_text, str):
            return output_text
        text = message.get("text")
        if isinstance(text, str):
            return text

    text = choice.get("text")
    if isinstance(text, str):
        return text

    delta = choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                    continue
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str) and text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)
    return None


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


def _escape_control_chars_in_json_strings(text: str) -> str:
    """
    Best-effort repair for JSON-ish output that contains raw control characters
    (e.g., newlines) inside quoted strings. JSON requires these to be escaped.
    """
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
                out.append(ch)
                continue
            if ch == "\\":
                escaped = True
                out.append(ch)
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
            continue

        if ch == '"':
            in_string = True
        out.append(ch)

    return "".join(out)


def _load_json_payload(content: str) -> dict:
    try:
        repaired_obj = json_repair.loads(content, strict=False)
        if isinstance(repaired_obj, dict):
            return repaired_obj
    except Exception:
        pass

    candidates = _json_candidates(content)
    last_err: json.JSONDecodeError | None = None
    for candidate in candidates:
        parsed, err = _json_loads_flexible(candidate)
        if parsed is not None:
            return parsed
        if err is not None:
            last_err = err
    if last_err is None:
        last_err = json.JSONDecodeError("No JSON candidates to parse", content, 0)
    raise last_err


def _json_loads_flexible(text: str) -> tuple[dict | None, json.JSONDecodeError | None]:
    try:
        return json.loads(text), None
    except json.JSONDecodeError as e:
        try:
            return json.loads(text, strict=False), None
        except json.JSONDecodeError as e2:
            return None, e2


def _json_candidates(content: str) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []

    def add(text: str) -> None:
        if not text:
            return
        if text in seen:
            return
        seen.add(text)
        candidates.append(text)

    add(content)
    cleaned = _strip_code_fence(content)
    add(cleaned)
    extracted = _extract_json_object(cleaned)
    add(extracted)

    escaped = _escape_control_chars_in_json_strings(cleaned)
    add(escaped)
    repaired = _repair_json_loose(cleaned)
    add(repaired)
    add(_escape_control_chars_in_json_strings(repaired))

    repaired_extracted = _repair_json_loose(extracted)
    add(repaired_extracted)
    add(_escape_control_chars_in_json_strings(repaired_extracted))

    return candidates


def _extract_json_object(text: str) -> str:
    in_string = False
    escaped = False
    depth = 0
    start: int | None = None
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
            continue
        if ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start : i + 1]
    return text


def _repair_json_loose(text: str) -> str:
    if not text:
        return text
    fixed = _insert_missing_commas(text)
    fixed = _remove_trailing_commas(fixed)
    fixed = _balance_brackets(fixed)
    return fixed


def _insert_missing_commas(text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    last_sig = ""
    saw_ws = False

    def should_insert() -> bool:
        if not saw_ws:
            return False
        return last_sig and last_sig not in "{[,:"

    for ch in text:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                last_sig = '"'
                saw_ws = False
            continue

        if ch.isspace():
            out.append(ch)
            saw_ws = True
            continue

        if ch == '"':
            if should_insert():
                out.append(",")
            out.append(ch)
            in_string = True
            saw_ws = False
            continue

        if ch in "{[":
            if should_insert():
                out.append(",")
            out.append(ch)
            last_sig = ch
            saw_ws = False
            continue

        if ch in "-0123456789tfn":
            if should_insert():
                out.append(",")
            out.append(ch)
            last_sig = ch
            saw_ws = False
            continue

        out.append(ch)
        last_sig = ch
        saw_ws = False

    return "".join(out)


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _balance_brackets(text: str) -> str:
    in_string = False
    escaped = False
    stack: list[str] = []
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch == "}":
            if stack and stack[-1] == "}":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "]":
                stack.pop()

    if not stack:
        return text
    return text + "".join(reversed(stack))
