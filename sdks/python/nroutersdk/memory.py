"""Client-side conversation memory.

The gateway is stateless between calls. This module stores messages locally and
returns copies that callers can pass as ``messages``.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any, Protocol

from nroutersdk._errors import nRouterRequestError

ChatMessage = dict[str, Any]
_ROLES = {"system", "user", "assistant", "tool", "developer"}
_TENANCY_KEYS = {"organizationid", "orgid", "teamid", "userid", "nrouterorg"}


class MemoryStore(Protocol):
    def load(self) -> list[ChatMessage]: ...
    def save(self, messages: list[ChatMessage]) -> None: ...


class ArrayMemoryStore:
    """In-process memory store. It writes nowhere by default."""

    def __init__(self, seed: list[ChatMessage] | None = None) -> None:
        self._messages = [_clone_message(m) for m in (seed or [])]

    def load(self) -> list[ChatMessage]:
        return [_clone_message(m) for m in self._messages]

    def save(self, messages: list[ChatMessage]) -> None:
        self._messages = [_clone_message(m) for m in messages]


def sliding_window(
    messages: list[ChatMessage],
    max_messages: int | None = None,
    preserve_system: bool = True,
) -> list[ChatMessage]:
    """Prune a message list to the most recent `max_messages`, preserving the index 0
    system/developer message by default.
    """
    if max_messages is None:
        return [_clone_message(m) for m in messages]
    if max_messages <= 0:
        return []
    if len(messages) <= max_messages:
        return [_clone_message(m) for m in messages]
    if preserve_system and messages and messages[0].get("role") in ("system", "developer"):
        if max_messages == 1:
            return [_clone_message(messages[-1])]
        tail_count = max_messages - 1
        tail = [_clone_message(m) for m in messages[-tail_count:]]
        return [_clone_message(messages[0])] + tail
    return [_clone_message(m) for m in messages[-max_messages:]]


class Memory:
    """A small async-safe wrapper around a message store."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        max_messages: int | None = None,
        preserve_system: bool = True,
    ) -> None:
        self._store = store or ArrayMemoryStore()
        self._lock = asyncio.Lock()
        self._max_messages = max_messages
        self._preserve_system = preserve_system

    async def add(self, message: ChatMessage) -> None:
        clean = _validate_message(message, "add()")
        async with self._lock:
            current = self._read()
            current.append(clean)
            self._write(current)

    async def messages(
        self,
        max_messages: int | None = None,
        preserve_system: bool | None = None,
    ) -> list[ChatMessage]:
        async with self._lock:
            msgs = self._read()
            max_limit = self._max_messages if max_messages is None else max_messages
            preserve = self._preserve_system if preserve_system is None else preserve_system
            if max_limit is not None:
                return sliding_window(msgs, max_limit, preserve)
            return msgs

    async def clear(self) -> None:
        async with self._lock:
            self._write([])

    def _read(self) -> list[ChatMessage]:
        raw = self._store.load()
        if not isinstance(raw, list):
            raise nRouterRequestError("MemoryStore.load() must return a list of messages.")
        return [_validate_message(m, f"MemoryStore.load()[{i}]") for i, m in enumerate(raw)]

    def _write(self, messages: list[ChatMessage]) -> None:
        self._store.save([_clone_message(m) for m in messages])


def create_array_store(seed: list[ChatMessage] | None = None) -> ArrayMemoryStore:
    return ArrayMemoryStore(seed)


def create_memory(
    store: MemoryStore | None = None,
    max_messages: int | None = None,
    preserve_system: bool = True,
) -> Memory:
    return Memory(store, max_messages=max_messages, preserve_system=preserve_system)


def _normalize_key(key: str) -> str:
    return key.lower().replace("_", "")


def _validate_message(message: Any, where: str) -> ChatMessage:
    if not isinstance(message, dict):
        raise nRouterRequestError(f"{where}: a message must be a dict.")
    for key in message:
        if _normalize_key(str(key)) in _TENANCY_KEYS:
            raise nRouterRequestError(
                f'{where}: a message must not carry the tenancy field "{key}".'
            )
    role = message.get("role")
    if role not in _ROLES:
        raise nRouterRequestError(
            f"{where}: role must be one of system, user, assistant, tool, developer."
        )
    content = message.get("content")
    tool_calls = message.get("tool_calls")
    has_tool_calls = isinstance(tool_calls, list) and len(tool_calls) > 0
    if content is None:
        if not has_tool_calls and role != "assistant":
            raise nRouterRequestError(f"{where}: content must be a string or content-parts list.")
    elif not isinstance(content, (str, list)):
        raise nRouterRequestError(f"{where}: content must be a string or content-parts list.")
    return _clone_message(message)


def _clone_message(message: ChatMessage) -> ChatMessage:
    return copy.deepcopy(message)
