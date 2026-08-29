"""nRouter SDK — one API key for models across six provider clouds.

Usage:
    from nroutersdk import nRouter

    client = nRouter()  # reads NROUTER_API_KEY from env
    response = client.chat.completions.create(
        model="anthropic/claude-sonnet-4-5-20250929",
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
    "nRouter",
    "AsyncnRouter",
    "DEFAULT_MODEL",
    "nRouterError",
    "nRouterRequestError",
    "nRouterGuardrailBlockedError",
    "nRouterAuthenticationError",
    "nRouterCreditError",
    "nRouterBudgetExceededError",
    "nRouterNotFoundError",
    "nRouterRateLimitError",
    "nRouterServiceError",
    "nRouterUnsupportedError",
    "nRouterResponseMeta",
    "PromptSelection",
    "PROMPT_WIRE_FIELDS",
    "SYSTEM_VARIABLE_NAMES",
    "prompt_template",
    "prompt_variables",
    "with_variables",
    "prompt_extra_body",
    "apply_prompt",
    "system_variable_conflicts",
    "build_sampling_params",
    "is_claude_model",
    "Memory",
    "MemoryStore",
    "create_array_store",
    "create_memory",
    "__version__",
]
