"""Friendly errors for OpenAI SDK methods not supported by nRouter."""

from __future__ import annotations


class nRouterUnsupportedError(NotImplementedError):
    """Raised when an OpenAI SDK method is not available via nRouter."""

    def __init__(self, feature: str, tip: str = "") -> None:
        msg = f"'{feature}' is not supported by nRouter."
        if tip:
            msg += f" {tip}"
        super().__init__(msg)


class _Blocked:
    """Descriptor that raises a clear error when accessed."""

    def __init__(self, name: str, tip: str = "") -> None:
        self._name = name
        self._tip = tip

    def __get__(self, obj, objtype=None):
        raise nRouterUnsupportedError(self._name, self._tip)


# ---------------------------------------------------------------------------
# Pre-built blockers for unsupported OpenAI resources.
# Audio, moderations, and rerank are NOW SUPPORTED — removed from blockers.
# ---------------------------------------------------------------------------

UNSUPPORTED = {
    "files": _Blocked(
        "client.files",
        "File management is not available via nRouter. "
        "Use your provider's file API directly.",
    ),
    "fine_tuning": _Blocked(
        "client.fine_tuning",
        "Fine-tuning is not available via nRouter. "
        "Use your provider's fine-tuning API directly.",
    ),
    "batches": _Blocked(
        "client.batches",
        "Batch API is not available via nRouter.",
    ),
    "beta": _Blocked(
        "client.beta (assistants / threads / realtime)",
        "Assistants / Threads API is not available via nRouter.",
    ),
    "vector_stores": _Blocked(
        "client.vector_stores",
        "Vector stores are not available via nRouter.",
    ),
    "uploads": _Blocked(
        "client.uploads",
        "Upload API is not available via nRouter.",
    ),
    "containers": _Blocked(
        "client.containers",
        "Containers API is not available via nRouter.",
    ),
    "conversations": _Blocked(
        "client.conversations",
        "Conversations API is not available via nRouter.",
    ),
    "evals": _Blocked(
        "client.evals",
        "Evals API is not available via nRouter.",
    ),
    "responses": _Blocked(
        "client.responses",
        "Responses API is not available via nRouter. "
        "Use client.chat.completions.create() instead.",
    ),
    "webhooks": _Blocked(
        "client.webhooks",
        "Webhooks API is not available via nRouter.",
    ),
}
