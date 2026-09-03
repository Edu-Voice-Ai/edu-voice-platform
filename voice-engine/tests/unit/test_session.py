"""Unit tests for SessionState, SessionManager, and isolation guarantees."""
import pytest
from app.session.state import SessionState, TurnStateEnum
from app.session.manager import SessionManager


@pytest.mark.asyncio
async def test_session_creation_and_isolation():
    manager = SessionManager()
    
    sess_a = await manager.create_session("sess_a", "org_1", "agent_1")
    sess_b = await manager.create_session("sess_b", "org_2", "agent_2")
    
    assert await manager.active_session_count() == 2
    
    # State mutation in Session A
    sess_a.append_message("user", "Hello from Org 1")
    sess_a.start_new_turn()
    
    # Verify Session B is totally untouched
    assert len(sess_a.messages) == 1
    assert len(sess_b.messages) == 0
    assert sess_a.turn_count == 1
    assert sess_b.turn_count == 0
    
    await manager.close_session("sess_a")
    assert await manager.active_session_count() == 1
    assert not sess_a.is_active


def test_turn_cancellation():
    sess = SessionState(session_id="test", organization_id="org", agent_id="agent")
    turn = sess.start_new_turn()
    assert turn.state == TurnStateEnum.LISTENING
    assert not turn.cancellation_token.is_cancelled
    
    turn.cancel(reason="Interrupted")
    assert turn.cancellation_token.is_cancelled
    assert turn.state == TurnStateEnum.INTERRUPTED
