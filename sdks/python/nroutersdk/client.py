"""nRouter client — thin wrapper around the OpenAI SDK."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

import httpx2 as httpx
from openai import APIStatusError
from openai import AsyncOpenAI as _AsyncOpenAI
from openai import OpenAI as _OpenAI

from nroutersdk._errors import (
    nRouterAuthenticationError,
    nRouterBudgetExceededError,
    nRouterCreditError,
    nRouterError,
    nRouterGuardrailBlockedError,
    nRouterNotFoundError,
    nRouterRateLimitError,
    nRouterRequestError,
    nRouterServiceError,
)
from nroutersdk._options import build_extra_body, vet_extra
from nroutersdk._response import nRouterResponseMeta
from nroutersdk._unsupported import UNSUPPORTED
from nroutersdk.sampling import build_sampling_params

if TYPE_CHECKING:
    from typing_extensions import Self

    # Route-specific compile-time proof for the resources this hybrid client
    # inherits from the bounded OpenAI dependency. Native nRouter additions
    # (Messages and video collection) are checked separately. Mypy resolves
    # every attribute chain here; one removed vendor resource fails the build.
    def _typecheck_openai_delegation(sync: _OpenAI, asynchronous: _AsyncOpenAI) -> None:
        _ = (
            sync.chat.completions.create,
            sync.completions.create,
            sync.embeddings.create,
            sync.images.generate,
            sync.audio.speech.create,
            sync.audio.transcriptions.create,
            sync.models.list,
            sync.models.retrieve,
            sync.responses.create,
            sync.audio.translations.create,
            asynchronous.chat.completions.create,
            asynchronous.completions.create,
            asynchronous.embeddings.create,
            asynchronous.images.generate,
            asynchronous.audio.speech.create,
            asynchronous.audio.transcriptions.create,
            asynchronous.models.list,
            asynchronous.models.retrieve,
            asynchronous.responses.create,
            asynchronous.audio.translations.create,
        )

_DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
_ENV_KEY = "NROUTER_API_KEY"
_ENV_BASE_URL = "NROUTER_BASE_URL"
_KEY_PREFIX = "sk-nrouter-"

#: Default model for the convenience wrapper.
#:
#: Kept in ONE place because it was previously a literal in a keyword default,
#: which is how it drifted to `gpt-4o` and stayed there. Any surface that needs
#: a default imports this name.
#:
#: It MUST be a model the gateway serves on `/v1/chat/completions`, because that
#: is the only wire `_nRouterChat.chat()` posts to — there is no per-model wire
#: switch here. The gateway resolves a provider endpoint PER WIRE and answers
#: 404 `model_unavailable_on_route` when the provider declares none, so an
#: Anthropic id (Messages-only) was a 404 out of the box for anyone who called
#: `client.nrouter.chat(messages)` without naming a model. `gpt-5.4-mini` is the
#: Rule #14 source-of-truth default and is served on this wire. Pinned by
#: `tests/test_defaults.py` and by `conformance/source_defaults.py`.
DEFAULT_MODEL = "gpt-5.4-mini"


def _resolve_api_key(api_key: str | None) -> str:
    resolved_key = api_key or os.environ.get(_ENV_KEY)
    if not resolved_key or not resolved_key.startswith(_KEY_PREFIX):
        raise ValueError(
            f"nRouter API keys must start with {_KEY_PREFIX!r}; pass api_key or set {_ENV_KEY}."
        )
    return resolved_key


def _resolve_base_url(base_url: str | None) -> str:
    """Resolve API base URL from parameter, NROUTER_BASE_URL env, or default."""
    return base_url or os.environ.get(_ENV_BASE_URL) or _DEFAULT_BASE_URL


# ---------------------------------------------------------------------------
# Helper: convert OpenAI APIStatusError into typed nRouter errors
# ---------------------------------------------------------------------------


def _maybe_raise_nrouter_error(err: APIStatusError) -> None:
    """Re-raise an OpenAI ``APIStatusError`` as the matching nRouter error.

    THE ENVELOPE. Measured against a live gateway on 2026-08-25, every gateway
    error body is built by `GatewayError::into_response` and looks like::

        {"error": {"type": "gateway_error", "message": "unknown model: gpt-9"}}

    Two things follow, and the pre-2.1.0 client got both wrong. There is no
    top-level ``code`` key, and the top-level ``error`` is an OBJECT, not a
    string. That client read ``body["code"]`` (always absent, so no branch ever
    matched) and ``body["error"]`` as the message (a dict, so a customer's log
    would have received a stringified mapping). It also read ``type``, which is
    the constant ``"gateway_error"`` on every single error and therefore
    classifies nothing.

    Classification is by STATUS plus the message, because status is what the
    gateway actually varies. The two 400s are separated on the message because
    that is the only signal present: a guardrail block and a malformed body
    share a status code.

    Returning ``None`` leaves the original ``APIStatusError`` to propagate,
    which is correct for anything outside this table — reclassifying an
    unrecognised failure would assert knowledge we do not have.
    """
    try:
        body = err.response.json()
    except (TypeError, ValueError):
        return
    if not isinstance(body, dict):
        return

    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message") or str(err)
        # The gateway names a stable code inside the error object when it can.
        # It is not the classifier — status is, per the note above — but where
        # two codes share one status it is the only thing that separates them.
        gateway_code = error.get("code") if isinstance(error.get("code"), str) else None
    elif isinstance(error, str):
        message = error
        gateway_code = None
    else:
        message = str(err)
        gateway_code = None

    headers = err.response.headers
    request_id = headers.get("x-nr-request-id") or body.get("request_id")
    status = err.status_code

    # A code, when the gateway sends one, is the strongest signal and the only
    # thing separating `rate_limit_exceeded` from `tpm_limit_exceeded`. The main
    # error path sends none — see the note above — so this is a preference, not
    # the primary route, and it stays forward-compatible with a gateway that
    # starts sending codes on every path.
    _BY_CODE = {
        "invalid_request": nRouterRequestError,
        "guardrail_blocked": nRouterGuardrailBlockedError,
        "invalid_api_key": nRouterAuthenticationError,
        "insufficient_credits": nRouterCreditError,
        "model_not_found": nRouterNotFoundError,
        "credit_check_failed": nRouterServiceError,
        "service_unavailable": nRouterServiceError,
    }
    if gateway_code in _BY_CODE:
        cls = _BY_CODE[gateway_code]
        if cls is nRouterAuthenticationError:
            raise cls(
                message,
                request_id=request_id,
                auth_reason=headers.get("x-nr-auth-reason"),
            ) from err
        if cls is nRouterServiceError:
            # `credit_check_failed` and `service_unavailable` share this class.
            # Without the code the exception reports the class default, so a
            # caller branching on the stable code gets the wrong one.
            raise cls(message, request_id=request_id, code=gateway_code) from err
        raise cls(message, request_id=request_id) from err
    if gateway_code in ("rate_limit_exceeded", "tpm_limit_exceeded"):
        retry_after_hdr = headers.get("retry-after")
        raise nRouterRateLimitError(
            message,
            request_id=request_id,
            limit_source=headers.get("x-nr-limit-source"),
            retry_after=(
                int(retry_after_hdr) if retry_after_hdr and retry_after_hdr.isdigit() else None
            ),
            code=gateway_code,
        ) from err
    if gateway_code:
        # A code we do NOT know must not fall through to status classification.
        # An unknown code on a 503 would become a retryable nRouterServiceError
        # carrying the fabricated code `service_unavailable` — a confident wrong
        # answer. Keep the base class and the code the gateway actually sent,
        # which is what the other SDKs' `Other` variant does.
        raise nRouterError(
            message, request_id=request_id, code=gateway_code, status_code=status
        ) from err

    if status == 400:
        if "guardrail" in message.lower():
            raise nRouterGuardrailBlockedError(message, request_id=request_id) from err
        raise nRouterRequestError(message, request_id=request_id) from err

    if status == 401:
        raise nRouterAuthenticationError(
            message,
            request_id=request_id,
            auth_reason=headers.get("x-nr-auth-reason"),
        ) from err

    if status == 402:
        # THREE conditions share this status and two are budget ceilings, whose
        # fix is the opposite of a credit shortfall's: raise the budget, not top
        # up. The gateway's own wording is the only discriminator it gives us,
        # and it is stable — `GatewayError::{BudgetExceeded, ScopedBudgetExceeded}`
        # both start their Display with "budget".
        if message.lstrip().lower().startswith("budget"):
            raise nRouterBudgetExceededError(message, request_id=request_id) from err
        raise nRouterCreditError(message, request_id=request_id) from err

    if status == 404:
        # Scoped to MODELS. A 404 is also a missing video job, an unknown MCP
        # server or an unknown agent run; calling those `model_not_found` is a
        # wrong answer with a confident stable code on it. Anything we cannot
        # identify keeps the base class rather than a fabricated one.
        if "model" in message.lower():
            raise nRouterNotFoundError(message, request_id=request_id) from err
        raise nRouterError(message, request_id=request_id, status_code=404) from err

    if status == 429:
        retry_after = headers.get("retry-after")
        raise nRouterRateLimitError(
            message,
            request_id=request_id,
            # GATE 7: read the source the gateway measured. `None` when it could
            # not attribute the refusal — never a guessed "rpm".
            limit_source=headers.get("x-nr-limit-source"),
            retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
            # `tpm_limit_exceeded` and `rate_limit_exceeded` share this status;
            # keep whichever the gateway named rather than the class default.
            code=gateway_code,
        ) from err

    if status == 500 or status == 503:
        raise nRouterServiceError(message, request_id=request_id, status_code=status) from err


# ---------------------------------------------------------------------------
# nRouter-specific resource namespaces
# ---------------------------------------------------------------------------


class _nRouterModels:
    """List the models this key can reach."""

    def __init__(self, client) -> None:
        self._c = client

    def list(self) -> dict:
        """List all models available through nRouter."""
        return cast(dict, self._c._nrouter_get("/v1/models"))


def _messages_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    prompt_template_id: str | None,
    prompt_variables: dict[str, str] | None,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Build one `/v1/messages` body, vetting the caller's escape hatch.

    THE MESSAGES WIRE IS THE ONLY ROUTE TO A MANAGED PROMPT FOR CLAUDE. The
    gateway resolves a provider endpoint per WIRE and answers 404
    `model_unavailable_on_route` for an Anthropic-family model on
    `/v1/chat/completions` (see `DEFAULT_MODEL` above and `tests/test_defaults.py`),
    and `_nRouterChat.chat()` posts only to chat-completions. So the named
    prompt options that path already had were unreachable for exactly the
    provider family this endpoint exists to serve; a Claude caller had to type
    the wire field names into `**kwargs` themselves.

    That also meant `**kwargs` was an UNVETTED body hatch on the one path they
    could use. `vet_extra` refuses two shapes here, both broken rather than
    merely unmodelled — a tenancy key (gateway §4f gate 5: tenancy comes from
    the authenticated virtual key alone, and a body-supplied identifier
    attributes no spend while reaching the provider as an unrecognized
    argument) and `__proto__`. Refused, never stripped: stripping leaves the
    caller believing they attributed spend somewhere, and that belief is wrong
    forever and silently. Everything else still passes straight through, which
    is what keeps an option this SDK does not model yet from being a blocker.

    Ordering mirrors the JS SDK's `buildFeatureBody`
    (`{...body, ...buildExtraBody(opts)}`, `sdks/js/src/client.ts` ->
    `sdks/js/src/options.ts`): the named option wins over a raw kwarg of the
    same wire name, so the two SDKs resolve that collision identically.

    `build_extra_body` is the ONE mapper to the spec's `extra_body_fields`
    (Rule #14) and OMITS what the caller did not set — omission and emptiness
    mean different things on this wire.
    """
    vet_extra(kwargs)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
        **kwargs,
    }
    payload.update(
        build_extra_body(
            prompt_template_id=prompt_template_id,
            prompt_variables=prompt_variables,
        )
    )
    return payload


class _Messages:
    """Anthropic-compatible Messages API.

    The buffered call is the reference provider slice. Streaming is refused
    explicitly until the SDK owns and tests an SSE parser; returning a JSON
    response while silently ignoring ``stream=True`` would be worse than a
    loud, actionable refusal.
    """

    def __init__(self, client) -> None:
        self._c = client

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        stream: bool = False,
        prompt_template_id: str | None = None,
        prompt_variables: dict[str, str] | None = None,
        **kwargs,
    ) -> dict:
        """Send a buffered Messages request, optionally with a managed prompt.

        Args:
            model: Model id served on `/v1/messages`.
            messages: Anthropic-shaped turns.
            max_tokens: Required by this wire.
            stream: Refused; see the class docstring.
            prompt_template_id: Override the org/team/key prompt assignment.
            prompt_variables: Jinja2 variables. Meaningful WITHOUT a template
                id too — the gateway then renders the assigned template with
                them.
            **kwargs: Any other body field, vetted by `vet_extra`.
        """
        if stream:
            raise NotImplementedError(
                "messages.create(stream=True) is not available until the SDK SSE stream contract is tested"
            )
        payload = _messages_payload(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            prompt_template_id=prompt_template_id,
            prompt_variables=prompt_variables,
            kwargs=kwargs,
        )
        return cast(dict, self._c._nrouter_post("/v1/messages", json=payload))

    def count_tokens(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs,
    ) -> dict:
        """Count input tokens without generating a response."""
        return cast(
            dict,
            self._c._nrouter_post(
                "/v1/messages/count_tokens",
                json={"model": model, "messages": messages, **kwargs},
            ),
        )


class _AsyncMessages:
    """Async Anthropic-compatible Messages API."""

    def __init__(self, client) -> None:
        self._c = client

    async def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        stream: bool = False,
        prompt_template_id: str | None = None,
        prompt_variables: dict[str, str] | None = None,
        **kwargs,
    ) -> dict:
        """See :meth:`_Messages.create`. Same surface, same vetting."""
        if stream:
            raise NotImplementedError(
                "messages.create(stream=True) is not available until the SDK SSE stream contract is tested"
            )
        payload = _messages_payload(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            prompt_template_id=prompt_template_id,
            prompt_variables=prompt_variables,
            kwargs=kwargs,
        )
        return cast(dict, await self._c._nrouter_post("/v1/messages", json=payload))

    async def count_tokens(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs,
    ) -> dict:
        """Count input tokens without generating a response."""
        return cast(
            dict,
            await self._c._nrouter_post(
                "/v1/messages/count_tokens",
                json={"model": model, "messages": messages, **kwargs},
            ),
        )


class _Videos:
    """Create, inspect, and download video generation jobs."""

    def __init__(self, client) -> None:
        self._c = client

    def create(self, *, model: str, prompt: str, **kwargs) -> dict:
        return cast(
            dict,
            self._c._nrouter_post(
                "/v1/videos",
                json={"model": model, "prompt": prompt, **kwargs},
            ),
        )

    def retrieve(self, video_id: str) -> dict:
        return cast(dict, self._c._nrouter_get(f"/v1/videos/{quote(video_id, safe='')}"))

    def download_content(self, video_id: str) -> bytes:
        return cast(
            bytes,
            self._c._nrouter_get_bytes(f"/v1/videos/{quote(video_id, safe='')}/content"),
        )


class _AsyncVideos:
    """Async video generation collection."""

    def __init__(self, client) -> None:
        self._c = client

    async def create(self, *, model: str, prompt: str, **kwargs) -> dict:
        return cast(
            dict,
            await self._c._nrouter_post(
                "/v1/videos",
                json={"model": model, "prompt": prompt, **kwargs},
            ),
        )

    async def retrieve(self, video_id: str) -> dict:
        return cast(
            dict,
            await self._c._nrouter_get(f"/v1/videos/{quote(video_id, safe='')}"),
        )

    async def download_content(self, video_id: str) -> bytes:
        return cast(
            bytes,
            await self._c._nrouter_get_bytes(f"/v1/videos/{quote(video_id, safe='')}/content"),
        )


# ---------------------------------------------------------------------------
# Chat wrapper with nRouter features
# ---------------------------------------------------------------------------


class _nRouterChat:
    """Extended chat with prompt template support + response metadata."""

    def __init__(self, client) -> None:
        self._c = client

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str = DEFAULT_MODEL,
        *,
        prompt_template_id: str | None = None,
        prompt_variables: dict[str, str] | None = None,
        guardrail_ids: list[str] | None = None,
        cache: bool | None = None,
        advanced_sampling: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        model_provider: str | None = None,
        stream: bool = False,
        **kwargs,
    ):
        """Send a chat completion with optional prompt template.

        Args:
            messages: Standard OpenAI messages list.
            model: Model name.
            prompt_template_id: Override org default prompt template.
            prompt_variables: Jinja2 variables for the template.
            guardrail_ids: Not supported per request; non-empty values raise.
            cache: Set false to force provider egress.
            advanced_sampling: When true, send validated temperature/top_p.
            stream: Stream the response.
            **kwargs: All OpenAI chat.completions.create() params.

        Returns:
            ChatCompletion. After the call, ``client.last_response`` has
            cost, cost status, model, token counts, and request ID.
        """
        extra_body: dict[str, Any] = kwargs.pop("extra_body", {}) or {}
        vet_extra(extra_body)

        extra_body.update(
            build_extra_body(
                prompt_template_id=prompt_template_id,
                prompt_variables=prompt_variables,
                guardrail_ids=guardrail_ids,
                cache=cache,
            )
        )
        kwargs.update(
            build_sampling_params(
                advanced=advanced_sampling,
                model=model,
                provider=model_provider,
                temperature=temperature,
                top_p=top_p,
            )
        )

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
        ``images``, ``audio``, ``responses``, ``models``, ``videos``,
        buffered ``messages.create`` and ``messages.count_tokens``

    nRouter extras:
        ``nrouter.chat()``, ``nrouter_models``, ``messages``, ``videos``,
        ``last_response``

    Args:
        api_key: nRouter API key (or ``NROUTER_API_KEY`` env var).
        base_url: Override default ``https://api.nrouter.ai/v1``.
    """

    # Block only resources the Rust gateway does not mount.
    files = UNSUPPORTED["files"]  # type: ignore[assignment]
    fine_tuning = UNSUPPORTED["fine_tuning"]  # type: ignore[assignment]
    batches = UNSUPPORTED["batches"]  # type: ignore[assignment]
    beta = UNSUPPORTED["beta"]  # type: ignore[assignment]
    vector_stores = UNSUPPORTED["vector_stores"]  # type: ignore[assignment]
    uploads = UNSUPPORTED["uploads"]  # type: ignore[assignment]
    containers = UNSUPPORTED["containers"]  # type: ignore[assignment]
    conversations = UNSUPPORTED["conversations"]  # type: ignore[assignment]
    evals = UNSUPPORTED["evals"]  # type: ignore[assignment]
    webhooks = UNSUPPORTED["webhooks"]  # type: ignore[assignment]

    nrouter_models: _nRouterModels
    messages: _Messages
    videos: _Videos  # type: ignore[assignment]
    nrouter: _nRouterChat
    last_response: nRouterResponseMeta | None

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize the nRouter client.

        Args:
            api_key: nRouter API key starting with 'sk-nrouter-'. Defaults to
                the NROUTER_API_KEY environment variable.
            base_url: Optional gateway base URL. Defaults to the NROUTER_BASE_URL
                environment variable or 'https://api.nrouter.ai/v1'.
            **kwargs: Extra arguments passed directly to OpenAI client constructor
                (e.g. timeout, max_retries, http_client).
        """
        resolved_key = _resolve_api_key(api_key)
        resolved_base = _resolve_base_url(base_url)

        super().__init__(api_key=resolved_key, base_url=resolved_base, **kwargs)

        self._nrouter_base = resolved_base.rstrip("/").removesuffix("/v1")
        self._nrouter_headers = {
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        }

        # Attach nRouter namespaces
        self.nrouter_models = _nRouterModels(self)
        self.messages = _Messages(self)
        self.videos = _Videos(self)  # type: ignore[assignment]
        self.nrouter = _nRouterChat(self)

        # Response metadata — updated after every API call
        self.last_response = None

        # Hook into httpx to capture response headers automatically
        self._client.event_hooks["response"].append(self._capture_nrouter_headers)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _capture_nrouter_headers(self, response: httpx.Response) -> None:
        """Capture canonical x-nr-* headers from every response."""
        headers = dict(response.headers)
        if any(k.startswith("x-nr-") for k in headers):
            self.last_response = nRouterResponseMeta.from_headers(headers)

    # -- error typing ------------------------------------------------------

    def _make_status_error(self, err_msg: str, *, body: object, response: httpx.Response):
        """Return the nRouter error for a failed response, else OpenAI's.

        THIS IS THE WIRING. Until 2.1.0 `_maybe_raise_nrouter_error` existed,
        was documented, was exported through the error classes — and was called
        from nowhere at all. Every typed error the README promised was
        unreachable; customers got a raw `openai.APIStatusError` and had to
        string-match it.

        `_make_status_error` is the correct seam rather than an httpx event
        hook: the OpenAI SDK exhausts its own retries BEFORE constructing the
        error, so a 429 that succeeds on retry never lands here, while a hook
        would raise on the first attempt and defeat the retry entirely.
        """
        try:
            _maybe_raise_nrouter_error(
                super()._make_status_error(err_msg, body=body, response=response)
            )
        except nRouterError as typed:
            return typed
        return super()._make_status_error(err_msg, body=body, response=response)

    # -- internal helpers --------------------------------------------------

    def _raise_for_status(self, r: httpx.Response) -> None:
        """Type a failure from the nRouter-native helpers.

        These calls bypass the OpenAI SDK's transport, so nothing else converts
        their failures. Before 2.1.0 they raised a bare
        `httpx.HTTPStatusError`, which is neither an OpenAI error nor an
        nRouter one — a third exception type from the same client object.
        """
        if r.is_success:
            return
        raise self._make_status_error_from_response(r)

    def _nrouter_get(self, path: str) -> dict:
        r = self._client.get(f"{self._nrouter_base}{path}", headers=self._nrouter_headers)
        self._raise_for_status(r)
        return cast(dict, r.json())

    def _nrouter_post(self, path: str, json: dict | None = None) -> dict:
        r = self._client.post(
            f"{self._nrouter_base}{path}",
            headers=self._nrouter_headers,
            json=json,
        )
        self._raise_for_status(r)
        return cast(dict, r.json())

    def _nrouter_get_bytes(self, path: str) -> bytes:
        r = self._client.get(f"{self._nrouter_base}{path}", headers=self._nrouter_headers)
        self._raise_for_status(r)
        return r.content


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


class AsyncnRouter(_AsyncOpenAI):
    """Async version of :class:`nRouter`. Same API surface."""

    # Block only resources the Rust gateway does not mount.
    files = UNSUPPORTED["files"]  # type: ignore[assignment]
    fine_tuning = UNSUPPORTED["fine_tuning"]  # type: ignore[assignment]
    batches = UNSUPPORTED["batches"]  # type: ignore[assignment]
    beta = UNSUPPORTED["beta"]  # type: ignore[assignment]
    vector_stores = UNSUPPORTED["vector_stores"]  # type: ignore[assignment]
    uploads = UNSUPPORTED["uploads"]  # type: ignore[assignment]
    containers = UNSUPPORTED["containers"]  # type: ignore[assignment]
    conversations = UNSUPPORTED["conversations"]  # type: ignore[assignment]
    evals = UNSUPPORTED["evals"]  # type: ignore[assignment]
    webhooks = UNSUPPORTED["webhooks"]  # type: ignore[assignment]

    nrouter_models: _nRouterModels
    messages: _AsyncMessages
    videos: _AsyncVideos  # type: ignore[assignment]
    nrouter: _nRouterChat
    last_response: nRouterResponseMeta | None

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize the AsyncnRouter client.

        Args:
            api_key: nRouter API key starting with 'sk-nrouter-'. Defaults to
                the NROUTER_API_KEY environment variable.
            base_url: Optional gateway base URL. Defaults to the NROUTER_BASE_URL
                environment variable or 'https://api.nrouter.ai/v1'.
            **kwargs: Extra arguments passed directly to AsyncOpenAI client constructor
                (e.g. timeout, max_retries, http_client).
        """
        resolved_key = _resolve_api_key(api_key)
        resolved_base = _resolve_base_url(base_url)

        super().__init__(api_key=resolved_key, base_url=resolved_base, **kwargs)

        self._nrouter_base = resolved_base.rstrip("/").removesuffix("/v1")
        self._nrouter_headers = {
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        }

        self.nrouter_models = _nRouterModels(self)
        self.messages = _AsyncMessages(self)
        self.videos = _AsyncVideos(self)  # type: ignore[assignment]
        self.nrouter = _nRouterChat(self)
        self.last_response = None

        # Hook into httpx to capture response headers automatically
        self._client.event_hooks["response"].append(self._capture_nrouter_headers)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def _capture_nrouter_headers(self, response: httpx.Response) -> None:
        """Capture canonical x-nr-* headers from every response."""
        headers = dict(response.headers)
        if any(k.startswith("x-nr-") for k in headers):
            self.last_response = nRouterResponseMeta.from_headers(headers)

    # -- error typing ------------------------------------------------------

    def _make_status_error(self, err_msg: str, *, body: object, response: httpx.Response):
        """Return the nRouter error for a failed response, else OpenAI's.

        THIS IS THE WIRING. Until 2.1.0 `_maybe_raise_nrouter_error` existed,
        was documented, was exported through the error classes — and was called
        from nowhere at all. Every typed error the README promised was
        unreachable; customers got a raw `openai.APIStatusError` and had to
        string-match it.

        `_make_status_error` is the correct seam rather than an httpx event
        hook: the OpenAI SDK exhausts its own retries BEFORE constructing the
        error, so a 429 that succeeds on retry never lands here, while a hook
        would raise on the first attempt and defeat the retry entirely.
        """
        try:
            _maybe_raise_nrouter_error(
                super()._make_status_error(err_msg, body=body, response=response)
            )
        except nRouterError as typed:
            return typed
        return super()._make_status_error(err_msg, body=body, response=response)

    def _raise_for_status(self, r: httpx.Response) -> None:
        """See `nRouter._raise_for_status`."""
        if r.is_success:
            return
        raise self._make_status_error_from_response(r)

    async def _nrouter_get(self, path: str) -> dict:
        r = await self._client.get(f"{self._nrouter_base}{path}", headers=self._nrouter_headers)
        self._raise_for_status(r)
        return cast(dict, r.json())

    async def _nrouter_post(self, path: str, json: dict | None = None) -> dict:
        r = await self._client.post(
            f"{self._nrouter_base}{path}",
            headers=self._nrouter_headers,
            json=json,
        )
        self._raise_for_status(r)
        return cast(dict, r.json())

    async def _nrouter_get_bytes(self, path: str) -> bytes:
        r = await self._client.get(f"{self._nrouter_base}{path}", headers=self._nrouter_headers)
        self._raise_for_status(r)
        return r.content
