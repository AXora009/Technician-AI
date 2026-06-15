"""Thin embedding adapter — provider selection via env vars."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=True)

EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "").lower()
EMBED_MODEL = os.environ.get("EMBED_MODEL")
EMBED_DIM = os.environ.get("EMBED_DIM")

if not EMBED_PROVIDER:
    if os.environ.get("VOYAGE_API_KEY"):
        EMBED_PROVIDER = "voyage"
    elif os.environ.get("GOOGLE_API_KEY"):
        EMBED_PROVIDER = "google"
    # OpenAI key is NOT auto-detected for embeddings — it's primarily the LLM key.
    # Set EMBED_PROVIDER=openai explicitly to enable OpenAI embeddings.

EMBEDDINGS_ENABLED = bool(EMBED_PROVIDER)

_DEFAULT_MODELS = {
    "voyage": "voyage-3-lite",
    "google": "gemini-embedding-001",
    "openai": "text-embedding-3-small",
}
if not EMBED_MODEL and EMBED_PROVIDER:
    EMBED_MODEL = _DEFAULT_MODELS.get(EMBED_PROVIDER)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    if EMBED_PROVIDER == "voyage":
        try:
            import voyageai
        except ImportError:
            raise ImportError("pip install voyageai")
        _client = voyageai.Client()

    elif EMBED_PROVIDER == "google":
        try:
            from google import genai
        except ImportError:
            raise ImportError("pip install google-genai")
        _client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    elif EMBED_PROVIDER == "openai":
        try:
            import openai
        except ImportError:
            raise ImportError("pip install openai")
        _client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("EMBED_BASE_URL"),
        )

    else:
        raise RuntimeError(
            f"Unknown EMBED_PROVIDER={EMBED_PROVIDER!r}. "
            "Set EMBED_PROVIDER to 'voyage', 'google', or 'openai', "
            "or set the corresponding API key env var."
        )
    return _client


def _embed_voyage(texts: list[str], input_type: str) -> list[list[float]]:
    client = _get_client()
    result = client.embed(texts, model=EMBED_MODEL, input_type=input_type)
    return result.embeddings


def _embed_google(texts: list[str], input_type: str) -> list[list[float]]:
    from google.genai import types

    client = _get_client()
    task_map = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}
    task_type = task_map.get(input_type, "RETRIEVAL_DOCUMENT")

    config = types.EmbedContentConfig(task_type=task_type)
    if EMBED_DIM:
        config.output_dimensionality = int(EMBED_DIM)

    result = client.models.embed_content(
        model=EMBED_MODEL, contents=texts, config=config
    )
    return [e.values for e in result.embeddings]


def _embed_openai(texts: list[str], input_type: str) -> list[list[float]]:
    client = _get_client()
    kwargs: dict = dict(model=EMBED_MODEL, input=texts)
    if EMBED_DIM:
        kwargs["dimensions"] = int(EMBED_DIM)
    result = client.embeddings.create(**kwargs)
    return [d.embedding for d in result.data]


def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    if not texts:
        return []
    if not EMBEDDINGS_ENABLED:
        raise RuntimeError("embed_texts called but no embedding provider is configured")

    if EMBED_PROVIDER == "voyage":
        return _embed_voyage(texts, input_type)
    elif EMBED_PROVIDER == "google":
        return _embed_google(texts, input_type)
    elif EMBED_PROVIDER == "openai":
        return _embed_openai(texts, input_type)
    else:
        raise RuntimeError(f"Unknown EMBED_PROVIDER={EMBED_PROVIDER!r}")
