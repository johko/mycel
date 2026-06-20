"""
Shared LLM access.

By default all inference goes through the Hugging Face router: authenticate
once with HF_TOKEN, name any served open-weights model, and the router picks a
provider. Pin one globally with HF_PROVIDER or per-model with a "model:provider"
suffix (e.g. "moonshotai/Kimi-K2-Instruct:groq").

A process may instead point at a local / self-hosted OpenAI-compatible endpoint
(e.g. an Ollama container) by passing a `BackendConfig` to `get_client`. The
chat-completion call path is identical — only the client's target changes — so
the same agent/planner code runs against hosted or on-device models.
"""

import asyncio
import json
import os

from huggingface_hub import AsyncInferenceClient
from pydantic import BaseModel

DEFAULT_MODEL = os.environ.get("MYCEL_MODEL", "moonshotai/Kimi-K2-Instruct")


class BackendConfig(BaseModel):
    """Where a process sends chat completions.

    `kind == "hf"` uses the Hugging Face router (default). `kind` of "ollama"
    or "openai-compatible" targets `base_url` (an OpenAI `/v1` endpoint), so a
    node can run its model on local hardware.
    """

    kind: str = "hf"
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


def get_client(backend: BackendConfig | None = None) -> AsyncInferenceClient:
    if backend is not None and backend.kind in ("ollama", "openai-compatible"):
        # OpenAI-compatible endpoint; api_key is required by the client but
        # ignored by Ollama, so default it to a placeholder.
        return AsyncInferenceClient(
            base_url=backend.base_url, api_key=backend.api_key or "local"
        )
    # token is read from the HF_TOKEN env var by the client itself
    return AsyncInferenceClient(provider=os.environ.get("HF_PROVIDER", "auto"))


async def chat_with_retry(client: AsyncInferenceClient, *, attempts: int = 3, **kwargs):
    """chat_completion with backoff — inference providers fail transiently."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await client.chat_completion(**kwargs)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(1 + attempt)
    raise last_error


def parse_tool_arguments(arguments) -> dict:
    """Tool-call arguments arrive as a JSON string or dict depending on provider."""
    if not arguments:
        return {}
    if isinstance(arguments, str):
        return json.loads(arguments)
    return dict(arguments)
