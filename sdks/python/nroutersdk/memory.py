"""Client-side conversation memory.

The gateway is stateless between calls. This module stores messages locally and
returns copies that callers can pass as ``messages``.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any, Dict, List, Optional, Protocol

from nroutersdk._errors import nRouterRequestError

ChatMessage = Dict[str, Any]
_ROLES = {"system", "user", "assistant"}
_TENANCY_KEYS = {"organizationid", "orgid", "teamid", "userid", "nrouterorg"}


class MemoryStore(Protocol):
    def load(self) -> List[ChatMessage]: ...
    def save(self, messages: List[ChatMessage]) -> None: ...


class ArrayMemoryStore:
    """In-process memory store. It writes nowhere by default."""

    def __init__(self, seed: Optional[List[ChatMessage]] = None) -> None:
        self._messages = [_clone_message(m) for m in (seed or [])]

    def load(self) -> List[ChatMessage]:
        return [_clone_message(m) for m in self._messages]

    def save(self, messages: List[ChatMessage]) -> None:
        self._messages = [_clone_message(m) for m in messages]


class Memory:
    """A small async-safe wrapper around a message store."""

    def __init__(self, store: Optional[MemoryStore] = None) -> None:
        self._store = store or ArrayMemoryStore()
        self._lock = asyncio.Lock()

    async def add(self, message: ChatMessage) -> None:
        clean = _validate_message(message, "add()")
        async with self._lock:
            current = self._read()
            current.append(clean)
            self._write(current)

    async def messages(self) -> List[ChatMessage]:
        async with self._lock:
            return self._read()

    async def clear(self) -> None:
        async with self._lock:
            self._write([])

    def _read(self) -> List[ChatMessage]:
        raw = self._store.load()
        if not isinstance(raw, list):
            raise nRouterRequestError("MemoryStore.load() must return a list of messages.")
        return [_validate_message(m, f"MemoryStore.load()[{i}]") for i, m in enumerate(raw)]

    def _write(self, messages: List[ChatMessage]) -> None:
        self._store.save([_clone_message(m) for m in messages])


def create_array_store(seed: Optional[List[ChatMessage]] = None) -> ArrayMemoryStore:
    return ArrayMemoryStore(seed)


def create_memory(store: Optional[MemoryStore] = None) -> Memory:
    return Memory(store)


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
        raise nRouterRequestError(f"{where}: role must be one of system, user, assistant.")
    content = message.get("content")
    if not isinstance(content, (str, list)):
        raise nRouterRequestError(f"{where}: content must be a string or content-parts list.")
    return _clone_message(message)


def _clone_message(message: ChatMessage) -> ChatMessage:
    return copy.deepcopy(message)
