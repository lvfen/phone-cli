"""会话生命周期管理。"""
import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    device_type: str
    device_id: str | None
    status: str
    timeout: float
    created_at: float = field(default_factory=time.time)
    acquired_at: float = 0.0
    last_active_at: float = field(default_factory=time.time)


class SessionManager:
    """管理所有 AI 会话的生命周期。线程安全。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, device_type: str, device_id: str | None = None,
               timeout: float = 300, status: str = "active") -> Session:
        now = time.time()
        session = Session(
            session_id=str(uuid.uuid4()), device_type=device_type,
            device_id=device_id, status=status, timeout=timeout,
            created_at=now, acquired_at=now if status == "active" else 0.0,
            last_active_at=now,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def release(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.status = "released"
            return session

    def expire(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.status = "expired"
            return session

    def activate(self, session_id: str, device_id: str) -> Session | None:
        now = time.time()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.status = "active"
            session.device_id = device_id
            session.acquired_at = now
            session.last_active_at = now
            return session

    def touch(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_active_at = time.time()

    def active_sessions(self) -> list[Session]:
        with self._lock:
            return [s for s in self._sessions.values() if s.status == "active"]

    def find_expired(self) -> list[Session]:
        now = time.time()
        with self._lock:
            return [
                s for s in self._sessions.values()
                if s.status == "active" and (now - s.last_active_at) > s.timeout
            ]
