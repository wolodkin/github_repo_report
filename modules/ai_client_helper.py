"""OpenAI-compatible chat client for structured JSON report responses."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from modules.common_helper import PROJECT_ROOT, read_api_key_file, utc_now_iso

logger = logging.getLogger(__name__)
_MODEL_LOGGED = False


class AIEndpointError(RuntimeError):
    """Raised for endpoint/auth/transport failures in AI calls."""


def get_active_model_config(config: dict[str, Any]) -> dict[str, Any]:
    ai = config.get("ai:config") or {}
    name = ai.get("active_model_name")
    models = ai.get("ai_model_config") or {}
    if not name or name not in models:
        raise KeyError(f"active_model_name not found in ai_model_config: {name!r}")
    return models[name]


def _is_local_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    return "ollama" in host


def _build_chat_url(endpoint_url: str, *, local_endpoint: bool) -> str:
    """
    Build the final chat URL.

    - Local Ollama: accept explicit /api/chat or /api/generate as-is.
      If only host/base is provided, default to /api/chat.
    - OpenAI-compatible: accept explicit .../chat/completions as-is,
      otherwise append /chat/completions.
    """
    base = endpoint_url.rstrip("/")
    if local_endpoint:
        if base.endswith("/api/chat") or base.endswith("/api/generate"):
            return base
        return base + "/api/chat"
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _extract_content(raw: dict[str, Any], *, local_endpoint: bool) -> str:
    """Extract assistant content from provider-specific response payload."""
    if local_endpoint:
        # Ollama /api/chat format:
        # {"message": {"role": "assistant", "content": "..."} ...}
        msg = raw.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str):
            raise AIEndpointError("Local AI response missing message.content")
        return content
    # OpenAI-compatible format:
    # {"choices":[{"message":{"content":"..."}}]}
    try:
        content = raw["choices"][0]["message"]["content"]
    except Exception as exc:
        raise AIEndpointError("Remote AI response missing choices[0].message.content") from exc
    if not isinstance(content, str):
        raise AIEndpointError("Remote AI content is not a string")
    return content


def _log_active_model_once(model_cfg: dict[str, Any]) -> None:
    global _MODEL_LOGGED
    if _MODEL_LOGGED:
        return
    endpoint_url = model_cfg.get("url", "")
    endpoint_kind = "local" if _is_local_endpoint(endpoint_url) else "remote"
    logger.info(
        "AI model active: model='%s' endpoint='%s' (%s)",
        model_cfg.get("model", "unknown"),
        endpoint_url,
        endpoint_kind,
    )
    _MODEL_LOGGED = True


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def truncate_to_num_ctx(text: str, num_ctx: int) -> str:
    budget = max(512, int(num_ctx * 0.85))
    est = _estimate_tokens(text)
    if est <= budget:
        return text
    logger.warning("Prompt ~%s tokens exceeds num_ctx budget ~%s; truncating", est, budget)
    max_chars = budget * 4
    return text[:max_chars] + "\n\n[... truncated to fit num_ctx ...]"


def chat_json(
    config: dict[str, Any],
    *,
    system_prompt: str,
    user_payload: str,
    debug_name: str,
) -> dict[str, Any]:
    model_cfg = get_active_model_config(config)
    _log_active_model_once(model_cfg)

    endpoint_url = model_cfg["url"]
    local_endpoint = _is_local_endpoint(endpoint_url)

    api_key = read_api_key_file(model_cfg.get("api_key_file", ""))
    if not local_endpoint and not api_key:
        raise AIEndpointError(
            "No API key for remote AI endpoint. "
            "Set api_key_file in config."
        )

    num_ctx = int(model_cfg.get("num_ctx", model_cfg.get("max_tokens", 8192)))
    user_payload = truncate_to_num_ctx(user_payload, num_ctx)

    url = _build_chat_url(endpoint_url, local_endpoint=local_endpoint)
    body: dict[str, Any] = {
        "model": model_cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        "temperature": float(model_cfg.get("temperature", 0.3)),
        "stream": bool(model_cfg.get("stream", False)),
        "response_format": {"type": "json_object"},
    }
    if local_endpoint:
        # Ollama-compatible endpoints expect num_ctx in options.
        body["options"] = {"num_ctx": num_ctx}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    timeout = int(model_cfg.get("timeout", 120))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AIEndpointError(f"AI API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIEndpointError(f"AI endpoint transport error: {exc}") from exc

    _maybe_store_debug(config, debug_name, raw)
    content = _extract_content(raw, local_endpoint=local_endpoint)
    return _parse_json_content(content)


def chat_json_validated(
    config: dict[str, Any],
    *,
    system_prompt: str,
    user_payload: str,
    debug_name: str,
    validate,
) -> dict[str, Any]:
    """Call chat_json once; on validation errors retry once with error feedback."""
    data = chat_json(
        config,
        system_prompt=system_prompt,
        user_payload=user_payload,
        debug_name=debug_name,
    )
    errors = validate(data)
    if not errors:
        return data
    retry_payload = (
        user_payload
        + "\n\nPrevious JSON failed validation. Fix and return only valid JSON.\nErrors:\n"
        + "\n".join(f"- {e}" for e in errors)
    )
    data = chat_json(
        config,
        system_prompt=system_prompt,
        user_payload=retry_payload,
        debug_name=debug_name + "_retry",
    )
    errors = validate(data)
    if errors:
        raise ValueError(f"JSON validation failed after retry: {errors}")
    return data


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _maybe_store_debug(config: dict[str, Any], name: str, payload: Any) -> None:
    ai = config.get("ai:config") or {}
    dbg = ai.get("ai_debug") or {}
    if not dbg.get("store_ai_responses"):
        return
    rel = dbg.get("store_ai_responses_path", "ai_debug/")
    out_dir = PROJECT_ROOT / rel.lstrip("/")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]
    path = out_dir / f"{safe}_{utc_now_iso().replace(':', '-')}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
