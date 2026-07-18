"""In-memory session store for the local FastAPI command center."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from greenmpc.ui.state import LiveControlSession


@dataclass
class StoredSession:
    session_id: str
    live: LiveControlSession
    lock: threading.RLock = field(default_factory=threading.RLock)
    request_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    executed_action_ids: set[str] = field(default_factory=set)


class SessionStore:
    """Thread-safe store for local demo simulator sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, StoredSession] = {}
        self._lock = threading.RLock()

    def create(self, live: LiveControlSession) -> StoredSession:
        with self._lock:
            session_id = uuid4().hex
            stored = StoredSession(session_id=session_id, live=live)
            self._sessions[session_id] = stored
            return stored

    def get(self, session_id: str) -> StoredSession:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"unknown session_id: {session_id}")
            return self._sessions[session_id]

    def replace(self, session_id: str, live: LiveControlSession) -> StoredSession:
        with self._lock:
            stored = StoredSession(session_id=session_id, live=live)
            self._sessions[session_id] = stored
            return stored


STORE = SessionStore()
