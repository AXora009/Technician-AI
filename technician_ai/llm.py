"""Thin LLM adapter — provider selection via env vars."""

from __future__ import annotations

import json
import os
import re

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "").lower()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL")
LLM_API_KEY = os.environ.get("LLM_API_KEY")

if not LLM_PROVIDER:
    if os.environ.get("ANTHROPIC_API_KEY"):
        LLM_PROVIDER = "anthropic"
    elif os.environ.get("OPENAI_API_KEY"):
        LLM_PROVIDER = "openai"
    elif os.environ.get("GOOGLE_API_KEY"):
        LLM_PROVIDER = "google"

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    if LLM_PROVIDER == "anthropic":
        try:
            import anthropic
        except ImportError:
            raise ImportError("pip install anthropic")
        _client = anthropic.Anthropic(
            api_key=LLM_API_KEY or os.environ.get("ANTHROPIC_API_KEY"),
        )
    elif LLM_PROVIDER == "openai":
        try:
            import openai
        except ImportError:
            raise ImportError("pip install openai")
        _client = openai.OpenAI(
            api_key=LLM_API_KEY or os.environ.get("OPENAI_API_KEY"),
            base_url=LLM_BASE_URL,
        )
    elif LLM_PROVIDER == "google":
        try:
            from google import genai
        except ImportError:
            raise ImportError("pip install google-genai")
        _client = genai.Client(
            api_key=LLM_API_KEY or os.environ.get("GOOGLE_API_KEY"),
        )
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. "
            "Set LLM_PROVIDER to 'anthropic', 'openai', or 'google', "
            "or set the corresponding API key env var for auto-detection."
        )
    return _client


def _chat_anthropic(
    system: str,
    user_message: str,
    model: str,
    max_tokens: int,
    json_schema: dict | None,
    effort: str | None,
    cache_system: bool,
) -> str:
    client = _get_client()

    if cache_system:
        system_param = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system_param = system

    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_param,
        messages=[{"role": "user", "content": user_message}],
    )

    if json_schema is not None:
        output_config: dict = {"format": {"type": "json_schema", "schema": json_schema}}
        if effort:
            output_config["effort"] = effort
        kwargs["output_config"] = output_config
    elif effort:
        kwargs["output_config"] = {"effort": effort}

    response = client.messages.create(**kwargs)
    return next((b.text for b in response.content if b.type == "text"), "")


def _chat_openai(
    system: str,
    user_message: str,
    model: str,
    max_tokens: int,
    json_schema: dict | None,
) -> str:
    client = _get_client()

    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    )

    if json_schema is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "strict": True, "schema": json_schema},
        }

    print(f"[llm_client] calling model={model} base_url={LLM_BASE_URL}")
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def _chat_google(
    system: str,
    user_message: str,
    model: str,
    max_tokens: int,
    json_schema: dict | None,
) -> str:
    from google.genai import types
    client = _get_client()

    config_kwargs: dict = dict(
        system_instruction=system,
        max_output_tokens=max_tokens,
    )
    if json_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = json_schema

    response = client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(**config_kwargs),
        contents=user_message,
    )
    text = response.text or ""
    if json_schema is not None:
        return _extract_json_fallback(text)
    return text


def _extract_json_fallback(text: str) -> str:
    """Best-effort JSON extraction when structured output isn't available."""
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            json.loads(match.group())
            return match.group()
        except json.JSONDecodeError:
            pass
    return text


def chat(
    system: str,
    user_message: str,
    model: str,
    max_tokens: int = 2048,
    json_schema: dict | None = None,
    effort: str | None = None,
    cache_system: bool = False,
) -> str:
    if LLM_PROVIDER == "anthropic":
        return _chat_anthropic(
            system, user_message, model, max_tokens, json_schema, effort, cache_system
        )
    elif LLM_PROVIDER == "openai":
        return _chat_openai(system, user_message, model, max_tokens, json_schema)
    elif LLM_PROVIDER == "google":
        return _chat_google(system, user_message, model, max_tokens, json_schema)
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. "
            "Set LLM_PROVIDER to 'anthropic', 'openai', or 'google', "
            "or set the corresponding API key env var."
        )
