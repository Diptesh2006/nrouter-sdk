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
    is_retryable,
    parse_retry_after,
    compute_jittered_backoff,
    MAX_RETRY_AFTER_SECONDS,
)
from nroutersdk._response import BudgetWarningInfo, nRouterResponseMeta
from nroutersdk._unsupported import nRouterUnsupportedError
from nroutersdk._version import __version__
from nroutersdk.client import DEFAULT_MODEL, AsyncnRouter, nRouter, parse_sse, uses_messages_wire
from nroutersdk.memory import (
    Memory,
    MemoryStore,
    create_array_store,
    create_memory,
    sliding_window,
)
from nroutersdk.prompts import (
    PROMPT_WIRE_FIELDS,
    SYSTEM_VARIABLE_NAMES,
    PromptSelection,
    apply_prompt,
    prompt_extra_body,
    prompt_template,
    prompt_variables,
    render_prompt,
    system_variable_conflicts,
    with_variables,
)
from nroutersdk.diagnostics import ReasoningExhaustionReport, diagnose_reasoning_exhaustion
from nroutersdk.media import VALID_AUDIO_FORMATS, validate_audio_format
from nroutersdk.sampling import build_sampling_params, is_claude_model

__all__ = [
    "DEFAULT_MODEL",
    "PROMPT_WIRE_FIELDS",
    "SYSTEM_VARIABLE_NAMES",
    "VALID_AUDIO_FORMATS",
    "AsyncnRouter",
    "BudgetWarningInfo",
    "Memory",
    "MemoryStore",
    "MAX_RETRY_AFTER_SECONDS",
    "PromptSelection",
    "ReasoningExhaustionReport",
    "__version__",
    "apply_prompt",
    "build_sampling_params",
    "create_array_store",
    "create_memory",
    "compute_jittered_backoff",
    "diagnose_reasoning_exhaustion",
    "is_claude_model",
    "is_retryable",
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
    "parse_retry_after",
    "parse_sse",
    "prompt_extra_body",
    "prompt_template",
    "prompt_variables",
    "render_prompt",
    "sliding_window",
    "system_variable_conflicts",
    "uses_messages_wire",
    "validate_audio_format",
    "with_variables",
]
