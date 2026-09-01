"""nRouter SDK — one API key for models across six provider clouds.

Usage:
    from nroutersdk import nRouter

    client = nRouter()  # reads NROUTER_API_KEY from env
    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    print(response.choices[0].message.content)
"""

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
from nroutersdk._response import nRouterResponseMeta
from nroutersdk._unsupported import nRouterUnsupportedError
from nroutersdk._version import __version__
from nroutersdk.client import DEFAULT_MODEL, AsyncnRouter, nRouter
from nroutersdk.memory import Memory, MemoryStore, create_array_store, create_memory
from nroutersdk.prompts import (
    PROMPT_WIRE_FIELDS,
    SYSTEM_VARIABLE_NAMES,
    PromptSelection,
    apply_prompt,
    prompt_extra_body,
    prompt_template,
    prompt_variables,
    system_variable_conflicts,
    with_variables,
)
from nroutersdk.sampling import build_sampling_params, is_claude_model

__all__ = [
    "DEFAULT_MODEL",
    "PROMPT_WIRE_FIELDS",
    "SYSTEM_VARIABLE_NAMES",
    "AsyncnRouter",
    "Memory",
    "MemoryStore",
    "PromptSelection",
    "__version__",
    "apply_prompt",
    "build_sampling_params",
    "create_array_store",
    "create_memory",
    "is_claude_model",
    "nRouter",
    "nRouterAuthenticationError",
    "nRouterBudgetExceededError",
    "nRouterCreditError",
    "nRouterError",
    "nRouterGuardrailBlockedError",
    "nRouterNotFoundError",
    "nRouterRateLimitError",
    "nRouterRequestError",
    "nRouterResponseMeta",
    "nRouterServiceError",
    "nRouterUnsupportedError",
    "prompt_extra_body",
    "prompt_template",
    "prompt_variables",
    "system_variable_conflicts",
    "with_variables",
]
