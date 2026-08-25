"""nRouter SDK — one API key for models across six provider clouds.

Usage:
    from nroutersdk import nRouter

    client = nRouter()  # reads NROUTER_API_KEY from env
    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    print(response.choices[0].message.content)
"""

from nroutersdk._errors import (
    nRouterAuthenticationError,
    nRouterCreditError,
    nRouterError,
    nRouterGuardrailBlockedError,
    nRouterNotFoundError,
    nRouterRateLimitError,
    nRouterRequestError,
    nRouterServiceError,
)
from nroutersdk._response import nRouterResponseMeta
from nroutersdk._unsupported import nRouterUnsupportedError
from nroutersdk._version import __version__
from nroutersdk.client import DEFAULT_MODEL, AsyncnRouter, nRouter

__all__ = [
    "nRouter",
    "AsyncnRouter",
    "DEFAULT_MODEL",
    "nRouterError",
    "nRouterRequestError",
    "nRouterGuardrailBlockedError",
    "nRouterAuthenticationError",
    "nRouterCreditError",
    "nRouterNotFoundError",
    "nRouterRateLimitError",
    "nRouterServiceError",
    "nRouterUnsupportedError",
    "nRouterResponseMeta",
    "__version__",
]
