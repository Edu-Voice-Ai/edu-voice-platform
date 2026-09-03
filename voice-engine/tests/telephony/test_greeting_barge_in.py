import pytest
import asyncio
from app.session.state import SessionState, TurnStateEnum, GreetingStateEnum
from app.pipeline.turn_manager import TurnManager
from app.pipeline.queues import PipelineQueueBundle


@pytest.mark.asyncio
async def test_greeting_barge_in_and_idempotency():
    queues = PipelineQueueBundle()
    session = SessionState(session_id="s_barge_test", organization_id="org1", agent_id="a1")
    
    # 1. Start greeting
    session.greeting_state = GreetingStateEnum.PLAYING
    session.is_greeting_playing = True
    turn = session.current_turn
    turn.state = TurnStateEnum.GREETING
    gen_id = turn.generation_id

    callback_called = []
    def on_barge_in(turn_id, generation_id):
        callback_called.append((turn_id, generation_id))

    tm = TurnManager(
        session=session,
        queues=queues,
        min_barge_in_duration_ms=100,
        on_barge_in_callback=on_barge_in
    )

    # 2. Simulate caller speaking during greeting (6 frames * 20ms = 120ms > 100ms threshold)
    transitions = []
    loud_frame = b"\x10\x10" * 160
    for _ in range(6):
        t = tm.handle_speech_frame(is_speech=True, frame_data=loud_frame, frame_duration_ms=20.0)
        if t:
            transitions.append(t)

    # 3. Verify Barge-In Triggered
    assert "BARGE_IN" in transitions
    assert session.is_greeting_playing is False
    assert session.greeting_state == GreetingStateEnum.COMPLETED
    assert session.user_has_floor is True
    assert gen_id in session.cancelled_generation_ids
    assert len(callback_called) == 1
    assert callback_called[0][1] == gen_id

    # 4. Verify stale generation is recognized as cancelled
    assert session.is_generation_cancelled(gen_id) is True
    assert session.is_generation_cancelled("some_future_gen") is False
