"""The client-side retry and timeout policy, observed at the transport.

WHY THIS FILE EXISTS. `nRouter` subclasses the vendor OpenAI client, which
retries twice by default on 408/409/429 and every 5xx. Inheriting that applied
it to `/v1/chat/completions`, `/v1/responses`, `/v1/images/generations`,
`/v1/audio/speech` and `/v1/videos` — billed, non-idempotent POSTs. Gateway
gate 8: a retry is a second call and a second BILL, the gateway reserves credit
once per customer request and owns retry and failover on its own side.

The tell that the defect was real: every other test file in this suite passes
`max_retries=0` explicitly. The suite was disabling what production shipped
with.

These tests COUNT ATTEMPTS AT THE TRANSPORT. They never assert on a recorded
constructor argument — `max_retries=0` sitting in a kwargs dict proves the value
was stored, not that it reached the retry loop, and the whole point is what goes
out on the wire.
"""

from __future__ import annotations

try:
    import openai._base_client as _obc
    httpx = getattr(_obc, "httpx2", getattr(_obc, "httpx", None))
    if httpx is None:
        import httpx2 as httpx
except (ImportError, AttributeError):
    try:
        import httpx2 as httpx
    except ImportError:
        import httpx
import pytest

from nroutersdk import AsyncnRouter, nRouter, nRouterBudgetExceededError
from nroutersdk.client import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT

KEY = "sk-nrouter-test-only-not-a-real-key"
BASE = "https://api.nrouter.ai/v1"


class Counter:
    """A transport that answers `status` and counts every attempt it sees."""

    def __init__(self, status: int, message: str = "upstream exploded") -> None:
        self.status = status
        self.message = message
        self.attempts = 0

    def _handle(self, _request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        return httpx.Response(
            self.status,
            json={"error": {"type": "gateway_error", "message": self.message}},
        )

    def sync(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def asynchronous(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)


def post(client: nRouter):
    """One billed POST through the vendor pipeline (not the native helpers)."""
    return client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": "hi"}],
        max_completion_tokens=16,
    )


# ---------------------------------------------------------------------------
# One attempt, by default, on every status the vendor would have retried
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [500, 429])
def test_a_billed_post_makes_exactly_one_attempt_by_default(status):
    """The vendor retries both of these twice. A 5xx or a 429 arriving after the
    gateway already accepted and dispatched the request means the "failed"
    attempt was a completed purchase; a retry buys a second one."""
    counter = Counter(status)
    with nRouter(
        api_key=KEY,
        base_url=BASE,
        http_client=httpx.Client(transport=counter.sync()),
    ) as client:
        with pytest.raises(Exception):
            post(client)
    assert counter.attempts == 1, (
        f"a billed POST made {counter.attempts} HTTP attempts on a {status}; "
        f"each one past the first is a second reservation and a second bill"
    )


@pytest.mark.asyncio
async def test_the_async_client_also_makes_exactly_one_attempt():
    counter = Counter(500)
    client = AsyncnRouter(
        api_key=KEY,
        base_url=BASE,
        http_client=httpx.AsyncClient(transport=counter.asynchronous()),
    )
    with pytest.raises(Exception):
        await client.chat.completions.create(
            model="gpt-5.5",
            messages=[{"role": "user", "content": "hi"}],
            max_completion_tokens=16,
        )
    await client.close()
    assert counter.attempts == 1


def test_the_default_is_zero_and_is_the_documented_constant():
    with nRouter(api_key=KEY, base_url=BASE) as client:
        assert DEFAULT_MAX_RETRIES == 0
        assert client.max_retries == DEFAULT_MAX_RETRIES


# ---------------------------------------------------------------------------
# Overridable: the default is a default, not a ceiling
# ---------------------------------------------------------------------------


def test_an_explicit_max_retries_from_the_caller_is_honoured():
    """A caller who knowingly wants retries gets them, and gets them at the
    transport — not merely stored on the client object."""
    counter = Counter(500)
    with nRouter(
        api_key=KEY,
        base_url=BASE,
        http_client=httpx.Client(transport=counter.sync()),
        max_retries=2,
    ) as client:
        with pytest.raises(Exception):
            post(client)
    assert counter.attempts == 3, "max_retries=2 must mean one attempt plus two retries"


# ---------------------------------------------------------------------------
# Timeout: explicit, documented, and not stolen from a custom transport
# ---------------------------------------------------------------------------


def test_the_default_timeout_is_the_documented_one():
    """600 s total, 10 s connect. With retries off a timeout is FINAL, so the
    number has to cover the slowest legitimate response — a long reasoning
    completion, a full-length speech synthesis, a large image or transcription."""
    assert DEFAULT_TIMEOUT == httpx.Timeout(600.0, connect=10.0)
    with nRouter(api_key=KEY, base_url=BASE) as client:
        assert client.timeout == DEFAULT_TIMEOUT
        assert client.timeout.connect == 10.0
        assert client.timeout.read == 600.0


def test_an_explicit_timeout_wins():
    with nRouter(api_key=KEY, base_url=BASE, timeout=httpx.Timeout(30.0)) as client:
        assert client.timeout == httpx.Timeout(30.0)


def test_a_custom_http_clients_own_timeout_is_not_overruled():
    """The README's corporate-proxy example passes a configured `httpx2.Client`.
    Forcing our default over it would silently discard that configuration; the
    vendor's own precedence is preserved instead."""
    configured = httpx.Client(timeout=httpx.Timeout(45.0, connect=3.0))
    with nRouter(api_key=KEY, base_url=BASE, http_client=configured) as client:
        assert client.timeout == httpx.Timeout(45.0, connect=3.0)


def test_a_custom_http_client_without_a_timeout_still_gets_the_default():
    """httpx's own default (5 s) is the vendor's structural sentinel for "never
    configured", so this client is not expressing an intent to overrule us."""
    with nRouter(
        api_key=KEY,
        base_url=BASE,
        http_client=httpx.Client(transport=Counter(200).sync()),
    ) as client:
        assert client.timeout == DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# The error translation still fires with retries off
# ---------------------------------------------------------------------------


def test_the_typed_error_translation_still_fires_with_retries_off():
    """`_make_status_error` used to be justified by "the vendor exhausts its
    retries before constructing the error". With the default at 0 there are no
    retries to exhaust, and the seam must still convert."""
    counter = Counter(402, "budget exceeded for team")
    with nRouter(
        api_key=KEY,
        base_url=BASE,
        http_client=httpx.Client(transport=counter.sync()),
    ) as client:
        with pytest.raises(nRouterBudgetExceededError) as caught:
            post(client)
    assert str(caught.value) == "budget exceeded for team"
    assert counter.attempts == 1
