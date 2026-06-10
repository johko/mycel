"""
Shared LLM access via Hugging Face Inference Providers.

All inference goes through the HF router: authenticate once with HF_TOKEN,
name any served open-weights model, and the router picks a provider.
Pin one globally with HF_PROVIDER or per-model with a "model:provider"
suffix (e.g. "moonshotai/Kimi-K2-Instruct:groq").
"""

import asyncio
import json
import os

from huggingface_hub import AsyncInferenceClient

DEFAULT_MODEL = os.environ.get("MYCEL_MODEL", "moonshotai/Kimi-K2-Instruct")


def get_client() -> AsyncInferenceClient:
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
