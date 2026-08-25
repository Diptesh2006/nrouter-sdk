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
# Pre-built blockers for OpenAI resources the Rust gateway does not mount.
#
# Derive the served set, never retype it:
#   grep -oE '"/v1[^"]*"' nrouter-rust-gateway/src/http/routes.rs | sort -u
#
# `responses` was in this table until 2.1.0, telling customers the Responses API
# was unavailable. It is mounted at `/v1/responses`, it was never actually
# applied to the class (the attribute was declared and the blocker ignored), and
# it answered 200 when measured on 2026-08-25. Audio, images, embeddings and
# videos are all served and are correctly absent here. `moderations` and
# `rerank` are NOT served and never were — the note claiming they were
# "NOW SUPPORTED" was wrong in both directions.
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
    "webhooks": _Blocked(
        "client.webhooks",
        "Webhooks API is not available via nRouter.",
    ),
}
