"""nRouter SDK — OpenAI-compatible client for the nRouter LLM gateway.

Usage:
    from nroutersdk import nRouter

    client = nRouter()  # reads NROUTER_API_KEY from env
    response = client.chat.completions.create(
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": "Hello!"}],
    )
"""

from nroutersdk._errors import (
    nRouterCreditError,
    nRouterGuardrailBlockedError,
    nRouterRateLimitError,
    nRouterError,
    nRouterServiceError,
)
from nroutersdk._response import nRouterResponseMeta
from nroutersdk._unsupported import nRouterUnsupportedError
from nroutersdk._version import __version__
from nroutersdk.client import AsyncnRouter, nRouter

__all__ = [
    "nRouter",
    "AsyncnRouter",
    "nRouterError",
    "nRouterGuardrailBlockedError",
    "nRouterCreditError",
    "nRouterRateLimitError",
    "nRouterServiceError",
    "nRouterUnsupportedError",
    "nRouterResponseMeta",
    "__version__",
]
