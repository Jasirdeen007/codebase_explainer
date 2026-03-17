from __future__ import annotations

from typing import Any

import requests
from django.conf import settings


def _configured() -> bool:
    api_key = getattr(settings, "LLM_API_KEY", "").strip()
    if api_key:
        return True

    base_url = getattr(settings, "LLM_BASE_URL", "").strip().lower()
    return base_url.startswith("http://localhost:11434") or base_url.startswith(
        "http://127.0.0.1:11434"
    )


def _serialize_sources(results: list[dict]) -> str:
    lines = []
    for idx, item in enumerate(results, start=1):
        path = (item.get("path") or item.get("file") or "unknown").replace("\\", "/")
        start = item.get("start_line")
        end = item.get("end_line")
        line_info = f" lines {start}-{end}" if start and end else ""
        snippet = " ".join((item.get("preview") or item.get("content") or "").split())
        if len(snippet) > 300:
            snippet = f"{snippet[:297]}..."
        lines.append(f"[{idx}] {path}{line_info}\n{snippet}")
    return "\n\n".join(lines)


def _extract_content(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        joined = "".join(text_parts).strip()
        return joined or None
    return None


def generate_reasoned_answer(question: str, results: list[dict]) -> str | None:
    if not _configured() or not results:
        return None

    system_prompt = (
        "You are a codebase analysis assistant. "
        "Answer the user's question using ONLY the provided source snippets. "
        "Be specific, concise, and avoid guessing. "
        "If evidence is weak, say that clearly."
    )
    user_prompt = (
        f"Question:\n{question}\n\n"
        "Retrieved sources:\n"
        f"{_serialize_sources(results)}\n\n"
        "Respond in this format:\n"
        "1) Direct answer (1-3 lines)\n"
        "2) Evidence (bullets with file paths)\n"
        "3) Next file to inspect\n"
    )

    base_url = getattr(settings, "LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": getattr(settings, "LLM_MODEL", "gpt-4o-mini"),
        "temperature": float(getattr(settings, "LLM_TEMPERATURE", 0.2)),
        "max_tokens": int(getattr(settings, "LLM_MAX_TOKENS", 650)),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {"Content-Type": "application/json"}
    api_key = getattr(settings, "LLM_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        if response.status_code >= 400:
            return None
        data = response.json()
        return _extract_content(data)
    except Exception:
        return None
