"""Optional Qwen-compatible LLM client (Ollama or OpenAI-compatible endpoint).

Rules:
  * Works with NO configuration - demo mode never calls this.
  * Any failure returns None; callers MUST fall back to deterministic logic.
  * Never used for numeric reconciliation, only extraction suggestions and
    narrative phrasing of numbers computed by Python.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from config.settings import settings


class QwenError(Exception):
    pass


def _post(url: str, payload: dict, timeout: int = 120, api_key: str | None = None) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    key = api_key if api_key is not None else settings.openai_api_key
    if key and "localhost" not in url and "127.0.0.1" not in url:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


def is_available() -> bool:
    if not settings.ai_enabled:
        return False
    if settings.qwen_mode == "ollama":
        try:
            _get(settings.ollama_base_url + "/api/tags")
            return True
        except Exception:
            return False
    if settings.qwen_mode == "gemini":
        return bool(settings.gemini_api_key)
    return bool(settings.openai_base_url)


def _get(url: str, timeout: int = 5) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def complete_json(system: str, user: str) -> dict | None:
    """Ask the model for strict JSON. Returns None on ANY failure."""
    try:
        if settings.qwen_mode == "ollama":
            payload = {
                "model": settings.qwen_model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "format": "json", "stream": False,
                "options": {"temperature": 0},
            }
            out = _post(settings.ollama_base_url + "/api/chat", payload)
            text = out.get("message", {}).get("content", "")
        elif settings.qwen_mode == "openai":
            payload = {
                "model": settings.qwen_model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0,
            }
            out = _post(settings.openai_base_url.rstrip("/") + "/chat/completions", payload)
            text = out["choices"][0]["message"]["content"]
        elif settings.qwen_mode == "gemini":
            # Gemini exposes an OpenAI-compatible chat-completions endpoint.
            payload = {
                "model": settings.gemini_model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0,
            }
            out = _post(GEMINI_BASE_URL + "/chat/completions", payload,
                        api_key=settings.gemini_api_key)
            text = out["choices"][0]["message"]["content"]
        else:
            return None
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):text.rfind("}") + 1]
        return json.loads(text)
    except Exception:
        return None
