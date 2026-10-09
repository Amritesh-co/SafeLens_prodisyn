"""
Minimal Ollama chat client (works with Ollama Cloud and a local Ollama server).

Config (environment):
    OLLAMA_API_KEY   - Bearer key for https://ollama.com (optional for local Ollama)
    OLLAMA_HOST      - Base URL, default https://ollama.com
    ASSISTANT_MODEL  - Model name, default gemma4:31b
    ASSISTANT_LLM_TIMEOUT_SECONDS - Per-request timeout, default 60
"""

import os

import requests


class LLMError(Exception):
    """Raised when the model provider cannot be reached or returns an error."""


def _config():
    return {
        'host': os.environ.get('OLLAMA_HOST', 'https://ollama.com').rstrip('/'),
        'api_key': os.environ.get('OLLAMA_API_KEY', '').strip(),
        'model': os.environ.get('ASSISTANT_MODEL', 'gemma4:31b'),
        'timeout': float(os.environ.get('ASSISTANT_LLM_TIMEOUT_SECONDS', '60')),
    }


def chat(messages, tools=None):
    """
    Send one non-streaming /api/chat request and return the assistant message dict:
        {"role": "assistant", "content": "...", "tool_calls": [...]}
    """
    cfg = _config()
    headers = {'Content-Type': 'application/json'}
    if cfg['api_key']:
        headers['Authorization'] = f"Bearer {cfg['api_key']}"

    payload = {
        'model': cfg['model'],
        'messages': messages,
        'stream': False,
        # Low temperature: answers should be factual reports of tool results.
        'options': {'temperature': 0.1},
    }
    if tools:
        payload['tools'] = tools

    try:
        resp = requests.post(
            f"{cfg['host']}/api/chat",
            json=payload,
            headers=headers,
            timeout=cfg['timeout'],
        )
    except requests.RequestException as exc:
        raise LLMError(f"Could not reach model provider: {exc.__class__.__name__}") from exc

    if resp.status_code != 200:
        raise LLMError(f"Model provider returned HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        message = resp.json().get('message') or {}
    except ValueError as exc:
        raise LLMError("Model provider returned invalid JSON") from exc

    return message


def model_name():
    return _config()['model']
