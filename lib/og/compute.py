"""0G Compute client — TEE-attested inference for signal generation.

Two modes:

1. **Direct** — operator already has a per-provider API key from
   `0g-compute-cli inference get-secret --provider <addr>`. We point the OpenAI
   SDK at the provider's `/v1/proxy` URL and store the returned `chatID` /
   `ZG-Res-Key` header alongside the signal. The chatID is later verified
   off-chain via `broker.inference.processResponse(providerAddress, chatID)`.

2. **Local proxy** — operator ran `0g-compute-cli inference serve --provider
   <addr> --port 3000`. We hit `http://localhost:3000` and the local proxy
   forwards + signs.

Either mode requires `OG_COMPUTE_BASE_URL` and `OG_COMPUTE_API_KEY` env vars.

This module imports lazily — `openai` is an optional dependency. If it isn't
installed, `infer()` returns a `ComputeError` with install instructions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class OGComputeError(RuntimeError):
    pass


ENV_BASE_URL = "OG_COMPUTE_BASE_URL"
ENV_API_KEY = "OG_COMPUTE_API_KEY"
ENV_DEFAULT_MODEL = "OG_COMPUTE_MODEL"
ENV_PROVIDER = "OG_COMPUTE_PROVIDER_ADDRESS"


@dataclass(frozen=True)
class InferenceResult:
    content: str
    chat_id: str
    model: str
    provider_address: str
    raw_response_id: str
    """The TEE attestation hook: pass `chat_id` to `broker.inference.processResponse(provider, chat_id)` to verify."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise OGComputeError(f"{name} must be set")
    return value


def infer(
    *,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    timeout: float = 60.0,
) -> InferenceResult:
    """Run a chat completion against a 0G Compute provider.

    Returns content + the TEE attestation chatID required to verify the
    response off-chain. The attestation chain is:

        chatID  ──►  broker.inference.processResponse(provider, chatID)
                       which validates the TEE signature against the
                       provider's attested signer set.
    """
    base_url = _require_env(ENV_BASE_URL)
    api_key = _require_env(ENV_API_KEY)
    provider = os.environ.get(ENV_PROVIDER, "")
    chosen_model = model or os.environ.get(ENV_DEFAULT_MODEL, "")
    if not chosen_model:
        raise OGComputeError(
            f"no model specified and {ENV_DEFAULT_MODEL} is unset; "
            "see `0g-compute-cli inference list-providers` for available models."
        )

    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError as exc:
        raise OGComputeError(
            "openai SDK not installed. Run: pip install openai>=1.0"
        ) from exc

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    response = client.chat.completions.create(
        model=chosen_model,
        messages=messages,
        temperature=temperature,
    )

    content = response.choices[0].message.content or ""
    chat_id = getattr(response, "id", "") or ""

    return InferenceResult(
        content=content,
        chat_id=chat_id,
        model=chosen_model,
        provider_address=provider,
        raw_response_id=chat_id,
    )
