"""Call session state machine and lifecycle manager foundation.

Maintains in-memory session tracking and manages transitions (CREATED -> CONNECTED -> DISCONNECTED)
with hooks for future realtime audio backpressure and disconnect cleanup.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class CallSessionState(str, Enum):
    """Lifecycle states of a telephony call session."""

    INITIATED = "initiated"
    RINGING = "ringing"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class CallSession(BaseModel):
    """Represents an active or historical telephony call session."""

    call_sid: str = Field(..., description="Unique provider call identifier")
    from_number: str = Field(..., description="Caller phone number")
    to_number: str = Field(..., description="Dialed DID number")
    organization_id: str | None = Field(default=None, description="Resolved tenant ID")
    agent_id: str | None = Field(default=None, description="Assigned AI agent ID")
    state: CallSessionState = Field(
        default=CallSessionState.INITIATED,
        description="Current session state",
    )
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Session creation timestamp in UTC",
    )
    connected_at: datetime | None = Field(
        default=None,
        description="Timestamp when call answered/connected",
    )
    ended_at: datetime | None = Field(
        default=None,
        description="Timestamp when call terminated",
    )
    disconnect_reason: str | None = Field(
        default=None,
        description="Reason for termination",
    )


class CallSessionLifecycleManager:
    """Manages active call sessions, lifecycle transitions, and cleanup."""

    def __init__(self) -> None:
        self._sessions: dict[str, CallSession] = {}

    def create_session(
        self,
        call_sid: str,
        from_number: str,
        to_number: str,
        organization_id: str | None = None,
        agent_id: str | None = None,
    ) -> CallSession:
        """Initialize and register a new call session."""
        session = CallSession(
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            organization_id=organization_id,
            agent_id=agent_id,
            state=CallSessionState.INITIATED,
        )
        self._sessions[call_sid] = session
        return session

    def get_session(self, call_sid: str) -> CallSession | None:
        """Retrieve an existing session by Call SID."""
        return self._sessions.get(call_sid)

    def transition_state(
        self,
        call_sid: str,
        new_state: CallSessionState,
        disconnect_reason: str | None = None,
    ) -> CallSession | None:
        """Transition session to a new state and record timing markers."""
        session = self._sessions.get(call_sid)
        if not session:
            return None

        session.state = new_state
        now = datetime.now(timezone.utc)

        if new_state == CallSessionState.CONNECTED and not session.connected_at:
            session.connected_at = now
        elif new_state in (CallSessionState.DISCONNECTED, CallSessionState.FAILED):
            session.ended_at = now
            if disconnect_reason:
                session.disconnect_reason = disconnect_reason

        return session

    def end_session(
        self,
        call_sid: str,
        reason: str | None = "normal_hangup",
    ) -> CallSession | None:
        """Explicitly disconnect and finalize a session."""
        return self.transition_state(
            call_sid=call_sid,
            new_state=CallSessionState.DISCONNECTED,
            disconnect_reason=reason,
        )

    def active_session_count(self) -> int:
        """Count of currently active (non-terminated) call sessions."""
        return sum(
            1
            for s in self._sessions.values()
            if s.state
            in (
                CallSessionState.INITIATED,
                CallSessionState.RINGING,
                CallSessionState.CONNECTED,
            )
        )
