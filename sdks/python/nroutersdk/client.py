"""nRouter client — thin wrapper around the OpenAI SDK."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from openai import APIStatusError, AsyncOpenAI as _AsyncOpenAI, OpenAI as _OpenAI

from nroutersdk._errors import (
    nRouterCreditError,
    nRouterGuardrailBlockedError,
    nRouterRateLimitError,
)
from nroutersdk._response import nRouterResponseMeta
from nroutersdk._unsupported import UNSUPPORTED

_DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
_ENV_KEY = "NROUTER_API_KEY"
_KEY_PREFIX = "sk-nrouter-"


def _resolve_api_key(api_key: Optional[str]) -> str:
    resolved_key = api_key or os.environ.get(_ENV_KEY)
    if not resolved_key or not resolved_key.startswith(_KEY_PREFIX):
        raise ValueError(
            f"nRouter API keys must start with {_KEY_PREFIX!r}; "
            f"pass api_key or set {_ENV_KEY}."
        )
    return resolved_key


# ---------------------------------------------------------------------------
# Helper: convert OpenAI APIStatusError into typed nRouter errors
# ---------------------------------------------------------------------------

def _maybe_raise_nrouter_error(err: APIStatusError) -> None:
    """Re-raise as a typed nRouter error if the response matches known codes."""
    try:
        body = err.response.json()
    except Exception:
        return

    code = body.get("code", "")
    message = body.get("error", str(err))
    request_id = body.get("request_id")

    if err.status_code == 400 and code == "guardrail_blocked":
        raise nRouterGuardrailBlockedError(
            message, request_id=request_id
        ) from err

    if err.status_code == 402 and code == "insufficient_credits":
        raise nRouterCreditError(message, request_id=request_id) from err

    if err.status_code == 429:
        limit_type = "tpm" if code == "tpm_limit_exceeded" else "rpm"
        raise nRouterRateLimitError(
            message, request_id=request_id, code=code, limit_type=limit_type
        ) from err


# ---------------------------------------------------------------------------
# nRouter-specific resource namespaces
# ---------------------------------------------------------------------------

class _Credits:
    """Check credit balance and transaction history."""

    def __init__(self, client) -> None:
        self._c = client

    def balance(self) -> dict:
        """Return current credit balance, reserved amount, and available credits."""
        return self._c._nrouter_get("/api/credits/balance")

    def history(self, limit: int = 50, offset: int = 0) -> dict:
        """Return credit transaction history."""
        return self._c._nrouter_get(f"/api/credits/history?limit={limit}&offset={offset}")


class _Guardrails:
    """View and inspect guardrails on your organization.

    Guardrails are applied automatically to every chat completion request.
    You cannot override them per-request — they are configured in the dashboard.
    """

    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> dict:
        """List all guardrails configured for your org."""
        return self._c._nrouter_get("/nrouter/guardrail/list")

    def get(self, guardrail_id: str) -> dict:
        """Get full config for a specific guardrail."""
        return self._c._nrouter_get(f"/nrouter/guardrail/info?guardrail_id={guardrail_id}")

    def logs(self, limit: int = 50) -> dict:
        """Get guardrail execution logs."""
        return self._c._nrouter_get(f"/nrouter/guardrail/logs?limit={limit}")


class _Prompts:
    """View and select prompt templates for your organization.

    Override which template to use per-request via ``client.nrouter.chat()``
    or ``extra_body={"nrouter_prompt_template_id": "..."}``
    """

    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> dict:
        """List all prompt templates."""
        return self._c._nrouter_get("/nrouter/prompt/list")

    def get(self, prompt_id: str) -> dict:
        """Get full template details including all versions."""
        return self._c._nrouter_get(f"/nrouter/prompt/info?prompt_id={prompt_id}")

    def versions(self, prompt_id: str) -> dict:
        """List all versions of a prompt template."""
        return self._c._nrouter_get(f"/nrouter/prompt/info?prompt_id={prompt_id}")

    def diff(self, version_id_1: str, version_id_2: str) -> dict:
        """Compare two prompt versions side by side."""
        return self._c._nrouter_get(
            f"/nrouter/prompt/version/diff?v1={version_id_1}&v2={version_id_2}"
        )


class _nRouterModels:
    """List available models and pricing."""

    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> dict:
        """List all models available through nRouter."""
        return self._c._nrouter_get("/v1/models")

    def pricing(self) -> dict:
        """Get per-model pricing information."""
        return self._c._nrouter_get("/api/models/pricing")


# ---------------------------------------------------------------------------
# Chat wrapper with nRouter features
# ---------------------------------------------------------------------------

class _nRouterChat:
    """Extended chat with prompt template support + response metadata."""

    def __init__(self, client) -> None:
        self._c = client

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        *,
        prompt_template_id: Optional[str] = None,
        prompt_variables: Optional[Dict[str, str]] = None,
        stream: bool = False,
        **kwargs,
    ):
        """Send a chat completion with optional prompt template.

        Args:
            messages: Standard OpenAI messages list.
            model: Model name.
            prompt_template_id: Override org default prompt template.
            prompt_variables: Jinja2 variables for the template.
            stream: Stream the response.
            **kwargs: All OpenAI chat.completions.create() params.

        Returns:
            ChatCompletion. After the call, ``client.last_response`` has
            cost, cost status, model, token counts, and request ID.
        """
        extra_body: Dict[str, Any] = kwargs.pop("extra_body", {}) or {}

        if prompt_template_id:
            extra_body["nrouter_prompt_template_id"] = prompt_template_id
        if prompt_variables:
            extra_body["nrouter_prompt_variables"] = prompt_variables

        return self._c.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream,
            extra_body=extra_body if extra_body else None,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------

class nRouter(_OpenAI):
    """OpenAI-compatible client pre-configured for nRouter.

    Every API call automatically captures response metadata in
    ``client.last_response`` — cost status, request ID, served model, token
    counts, and the source of a rate-limit response.

    Supported:
        ``chat.completions``, ``completions``, ``embeddings``,
        ``images``, ``models``

    nRouter extras:
        ``nrouter.chat()``, ``credits``, ``guardrails``, ``prompts``,
        ``nrouter_models``, ``last_response``

    Args:
        api_key: nRouter API key (or ``NROUTER_API_KEY`` env var).
        base_url: Override default ``https://api.nrouter.ai/v1``.
    """

    # Supported: chat, completions, embeddings, images, models, audio, moderations
    # Block unsupported OpenAI resources (audio/moderations now supported)
    files = UNSUPPORTED["files"]  # type: ignore[assignment]
    fine_tuning = UNSUPPORTED["fine_tuning"]  # type: ignore[assignment]
    batches = UNSUPPORTED["batches"]  # type: ignore[assignment]
    beta = UNSUPPORTED["beta"]  # type: ignore[assignment]
    vector_stores = UNSUPPORTED["vector_stores"]  # type: ignore[assignment]
    uploads = UNSUPPORTED["uploads"]  # type: ignore[assignment]
    containers = UNSUPPORTED["containers"]  # type: ignore[assignment]
    conversations = UNSUPPORTED["conversations"]  # type: ignore[assignment]
    evals = UNSUPPORTED["evals"]  # type: ignore[assignment]
    responses = UNSUPPORTED["responses"]  # type: ignore[assignment]
    webhooks = UNSUPPORTED["webhooks"]  # type: ignore[assignment]

    credits: _Credits
    guardrails: _Guardrails
    prompts: _Prompts
    nrouter_models: _nRouterModels
    nrouter: _nRouterChat
    last_response: Optional[nRouterResponseMeta]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ) -> None:
        resolved_key = _resolve_api_key(api_key)
        resolved_base = base_url or _DEFAULT_BASE_URL

        super().__init__(api_key=resolved_key, base_url=resolved_base, **kwargs)

        self._nrouter_base = resolved_base.rstrip("/").removesuffix("/v1")
        self._nrouter_headers = {
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        }

        # Attach nRouter namespaces
        self.credits = _Credits(self)
        self.guardrails = _Guardrails(self)
        self.prompts = _Prompts(self)
        self.nrouter_models = _nRouterModels(self)
        self.nrouter = _nRouterChat(self)

        # Response metadata — updated after every API call
        self.last_response = None

        # Hook into httpx to capture response headers automatically
        self._client.event_hooks["response"].append(self._capture_nrouter_headers)

    def _capture_nrouter_headers(self, response: httpx.Response) -> None:
        """Capture canonical x-nr-* headers from every response."""
        headers = dict(response.headers)
        if any(k.startswith("x-nr-") for k in headers):
            self.last_response = nRouterResponseMeta.from_headers(headers)

    # -- internal helpers --------------------------------------------------

    def _nrouter_get(self, path: str) -> dict:
        r = httpx.get(f"{self._nrouter_base}{path}", headers=self._nrouter_headers)
        r.raise_for_status()
        return r.json()

    def _nrouter_post(self, path: str, json: Optional[dict] = None) -> dict:
        r = httpx.post(
            f"{self._nrouter_base}{path}",
            headers=self._nrouter_headers,
            json=json,
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

class AsyncnRouter(_AsyncOpenAI):
    """Async version of :class:`nRouter`. Same API surface."""

    # Supported: chat, completions, embeddings, images, models, audio, moderations
    # Block unsupported OpenAI resources (audio/moderations now supported)
    files = UNSUPPORTED["files"]  # type: ignore[assignment]
    fine_tuning = UNSUPPORTED["fine_tuning"]  # type: ignore[assignment]
    batches = UNSUPPORTED["batches"]  # type: ignore[assignment]
    beta = UNSUPPORTED["beta"]  # type: ignore[assignment]
    vector_stores = UNSUPPORTED["vector_stores"]  # type: ignore[assignment]
    uploads = UNSUPPORTED["uploads"]  # type: ignore[assignment]
    containers = UNSUPPORTED["containers"]  # type: ignore[assignment]
    conversations = UNSUPPORTED["conversations"]  # type: ignore[assignment]
    evals = UNSUPPORTED["evals"]  # type: ignore[assignment]
    responses = UNSUPPORTED["responses"]  # type: ignore[assignment]
    webhooks = UNSUPPORTED["webhooks"]  # type: ignore[assignment]

    credits: _Credits
    guardrails: _Guardrails
    prompts: _Prompts
    nrouter_models: _nRouterModels
    nrouter: _nRouterChat
    last_response: Optional[nRouterResponseMeta]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ) -> None:
        resolved_key = _resolve_api_key(api_key)
        resolved_base = base_url or _DEFAULT_BASE_URL

        super().__init__(api_key=resolved_key, base_url=resolved_base, **kwargs)

        self._nrouter_base = resolved_base.rstrip("/").removesuffix("/v1")
        self._nrouter_headers = {
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        }

        self.credits = _Credits(self)
        self.guardrails = _Guardrails(self)
        self.prompts = _Prompts(self)
        self.nrouter_models = _nRouterModels(self)
        self.nrouter = _nRouterChat(self)
        self.last_response = None

        # Hook into httpx to capture response headers automatically
        self._client.event_hooks["response"].append(self._capture_nrouter_headers)

    async def _capture_nrouter_headers(self, response: httpx.Response) -> None:
        """Capture canonical x-nr-* headers from every response."""
        headers = dict(response.headers)
        if any(k.startswith("x-nr-") for k in headers):
            self.last_response = nRouterResponseMeta.from_headers(headers)

    def _nrouter_get(self, path: str) -> dict:
        r = httpx.get(f"{self._nrouter_base}{path}", headers=self._nrouter_headers)
        r.raise_for_status()
        return r.json()

    def _nrouter_post(self, path: str, json: Optional[dict] = None) -> dict:
        r = httpx.post(
            f"{self._nrouter_base}{path}",
            headers=self._nrouter_headers,
            json=json,
        )
        r.raise_for_status()
        return r.json()
