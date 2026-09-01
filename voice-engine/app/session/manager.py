"""SessionManager maintaining active isolated sessions."""
from typing import Dict, Optional, List
import asyncio
from app.session.state import SessionState
from app.core.errors import SessionNotFoundError, SessionClosedError
from app.core.logging import get_logger

logger = get_logger("session_manager")


class SessionManager:
    """Thread-safe session registry and lifecycle manager."""
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        organization_id: str,
        agent_id: str,
        call_id: Optional[str] = None,
        language: str = "te-IN",
        client_sample_rate: int = 16000
    ) -> SessionState:
        """Create and register a new isolated SessionState."""
        async with self._lock:
            session = SessionState(
                session_id=session_id,
                organization_id=organization_id,
                agent_id=agent_id,
                call_id=call_id,
                language=language,
                client_sample_rate=client_sample_rate
            )
            self._sessions[session_id] = session
            logger.info(f"Created session {session_id} for org={organization_id}, agent={agent_id}", extra={"session_id": session_id})
            return session

    async def get_session(self, session_id: str) -> SessionState:
        """Retrieve an active session by session_id."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise SessionNotFoundError(session_id)
            if not session.is_active:
                raise SessionClosedError(session_id)
            return session

    async def close_session(self, session_id: str) -> Optional[SessionState]:
        """Close and remove an active session."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.close()
                logger.info(f"Closed session {session_id}", extra={"session_id": session_id})
            return session

    async def active_session_count(self) -> int:
        """Return the count of active sessions."""
        async with self._lock:
            return len(self._sessions)

    async def list_active_session_ids(self) -> List[str]:
        """List all active session IDs."""
        async with self._lock:
            return list(self._sessions.keys())


_session_manager_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Retrieve global SessionManager singleton."""
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager()
    return _session_manager_instance
