"""Minimal optional model hook.

The grading container runs the official DeepSeek Harness, which supplies the
model. A Skill therefore must not depend on its own API credentials: every
script here is deterministic, and the agent performs the semantic work by
following SKILL.md.

This module exists only for local development convenience. When no key is
configured every helper returns ``None`` and callers fall back to their
deterministic path.
"""

import json
import os

BASE = os.environ.get("BSK_API_BASE", "").rstrip("/")
KEY = os.environ.get("BSK_API_KEY", "")
MODEL = os.environ.get("BSK_MODEL", "")
TIMEOUT = float(os.environ.get("BSK_TIMEOUT", "60"))


def available():
    return bool(BASE and KEY and MODEL)


def status():
    return {
        "enabled": available(),
        "note": ("Skill 不依赖自有模型凭据；语义工作由宿主 Agent 按 SKILL.md 执行，"
                 "脚本保持确定性。"),
    }


def chat(system, user, temperature=0.2, max_tokens=2000, json_mode=False):
    if not available():
        return None
    try:
        import urllib.request
    except ImportError:
        return None
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/chat/completions", data=data,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + KEY})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            parsed = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    try:
        return parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def chat_json(system, user, **kwargs):
    raw = chat(system, user, json_mode=True, **kwargs)
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except ValueError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                return None
    return None
