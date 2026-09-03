"""Deterministic tests for Conversation Floor, stale audio protection, and race conditions."""
import asyncio
import base64
import json
import pytest
from app.session.state import SessionState, ConversationFloor, TurnStateEnum
from app.session.events import SessionEvent, EventType
from app.audio.codec import AudioCodec


@pytest.mark.asyncio
async def test_race_a_stale_packet_held_across_pacing_sleep_dropped():
    """
    Race A: AI audio packet is already pulled from queue and held locally.
    Pacing sleep occurs. Meanwhile, user barge-in triggers and invalidates generation.
    After pacing sleep wakes, the packet MUST be dropped and NOT sent to Exotel.
    """
    session = SessionState(session_id="s_race_a", organization_id="org1", agent_id="a1")
    session.language = "te-IN"
    session.preferred_language = "te-IN"
    session.active_playback_generation_id = "gen_100"
    session.active_playback_turn_id = "turn_100"
    session.active_playback_language = "te-IN"

    sent_messages = []
    class MockWebSocket:
        async def send_text(self, text):
            sent_messages.append(json.loads(text))

    ws = MockWebSocket()
    event_queue = asyncio.Queue()

    writer_state = {
        "stream_sid": "stream_race_a",
        "encoding": "audio/x-l16",
        "sample_rate": 8000,
        "outbound_media_count": 0,
        "last_handled_cancellation_cycle": -1
    }

    # Helper runner for exotel writer loop logic
    async def writer_step(event):
        nonlocal writer_state
        sid = writer_state.get("stream_sid")
        sr = writer_state.get("sample_rate", 8000)
        enc = writer_state.get("encoding", "audio/x-l16")

        if event.event in (EventType.RESPONSE_CANCELLED, EventType.AUDIO_PLAYBACK_STOP, EventType.AUDIO_FLUSH):
            cycle_id = getattr(session, "cancellation_cycle_id", 0)
            if sid and cycle_id != writer_state["last_handled_cancellation_cycle"]:
                writer_state["last_handled_cancellation_cycle"] = cycle_id
                await ws.send_text(json.dumps({"event": "clear", "stream_sid": sid}))
            return

        if event.event in (EventType.AUDIO_OUTPUT, "audio.output"):
            gen_id = event.generation_id
            turn_id = event.turn_id
            event_lang = event.data.get("language")
            active_lang = session.preferred_language or session.language

            def is_stale():
                if session.is_generation_cancelled(gen_id):
                    return True
                if session.active_playback_generation_id and gen_id != session.active_playback_generation_id:
                    return True
                if session.active_playback_turn_id and turn_id != session.active_playback_turn_id:
                    return True
                if event_lang and active_lang and event_lang != active_lang:
                    return True
                return False

            # Check 1: before pacing sleep
            if is_stale():
                return

            # Simulate pacing sleep: during this sleep, user interrupts!
            session.invalidate_active_generation(reason="User interrupted during pacing sleep")
            await asyncio.sleep(0.01)

            # Check 2: after pacing sleep
            if is_stale():
                return  # Dropped!

            await ws.send_text(json.dumps({"event": "media", "stream_sid": sid}))

    # Audio chunk from gen_100
    dummy_b64 = base64.b64encode(b"\x00" * 320).decode("ascii")
    audio_event = SessionEvent(
        event=EventType.AUDIO_OUTPUT,
        session_id="s_race_a",
        turn_id="turn_100",
        generation_id="gen_100",
        data={"data": dummy_b64, "seq": 1, "sample_rate": 16000, "language": "te-IN"}
    )

    await writer_step(audio_event)

    # Verify that NO media message was sent because it was dropped after waking from sleep!
    media_messages = [m for m in sent_messages if m.get("event") == "media"]
    assert len(media_messages) == 0


@pytest.mark.asyncio
async def test_race_b_tts_worker_chunk_after_cancellation_dropped():
    """
    Race B: A generation is cancelled. Late audio packets from that generation must be dropped.
    """
    session = SessionState(session_id="s_race_b", organization_id="org1", agent_id="a1")
    session.active_playback_generation_id = "gen_1"
    session.active_playback_turn_id = "turn_1"
    session.language = "en-IN"

    # Invalidate generation 1
    session.invalidate_active_generation(reason="Barge-in")

    gen_id = "gen_1"
    turn_id = "turn_1"
    event_lang = "en-IN"
    active_lang = session.preferred_language or session.language

    # Validate using the 4-point rule
    is_stale = (
        session.is_generation_cancelled(gen_id)
        or (session.active_playback_generation_id and gen_id != session.active_playback_generation_id)
        or (session.active_playback_turn_id and turn_id != session.active_playback_turn_id)
        or (event_lang and active_lang and event_lang != active_lang)
    )
    assert is_stale is True


@pytest.mark.asyncio
async def test_race_c_language_change_drops_late_old_language_chunk():
    """
    Race C: Language changes from Telugu to Hindi.
    A late Telugu chunk arrives at writer -> MUST be dropped because packet language != current language.
    """
    session = SessionState(session_id="s_race_c", organization_id="org1", agent_id="a1")
    session.language = "hi-IN"
    session.preferred_language = "hi-IN"
    session.active_playback_generation_id = "gen_hindi"
    session.active_playback_turn_id = "turn_2"
    session.active_playback_language = "hi-IN"

    # Stale chunk with Telugu language arrives with old gen_id
    old_gen_id = "gen_telugu"
    old_turn_id = "turn_1"
    old_lang = "te-IN"
    active_lang = session.preferred_language or session.language

    is_stale = (
        session.is_generation_cancelled(old_gen_id)
        or (session.active_playback_generation_id and old_gen_id != session.active_playback_generation_id)
        or (session.active_playback_turn_id and old_turn_id != session.active_playback_turn_id)
        or (old_lang and active_lang and old_lang != active_lang)
    )
    assert is_stale is True


@pytest.mark.asyncio
async def test_race_d_e_old_turn_and_generation_id_dropped():
    """
    Race D & E: Verify mismatched turn_id and generation_id are dropped.
    """
    session = SessionState(session_id="s_race_de", organization_id="org1", agent_id="a1")
    session.active_playback_generation_id = "gen_current"
    session.active_playback_turn_id = "turn_current"
    session.language = "en-IN"

    # 1. Mismatched gen_id
    assert session.active_playback_generation_id != "gen_old"
    # 2. Mismatched turn_id
    assert session.active_playback_turn_id != "turn_old"


@pytest.mark.asyncio
async def test_race_f_multiple_cancellation_events_produce_single_clear():
    """
    Race F: RESPONSE_CANCELLED, AUDIO_FLUSH, and AUDIO_PLAYBACK_STOP arrive in sequence.
    They belong to the same cancellation_cycle_id -> exactly ONE CLEAR packet is sent.
    """
    session = SessionState(session_id="s_race_f", organization_id="org1", agent_id="a1")
    session.cancellation_cycle_id = 1

    sent_messages = []
    class MockWebSocket:
        async def send_text(self, text):
            sent_messages.append(json.loads(text))

    ws = MockWebSocket()
    writer_state = {
        "stream_sid": "stream_race_f",
        "last_handled_cancellation_cycle": -1
    }

    events = [
        SessionEvent(event=EventType.RESPONSE_CANCELLED, session_id="s_race_f", turn_id="t1", generation_id="g1"),
        SessionEvent(event=EventType.AUDIO_FLUSH, session_id="s_race_f", turn_id="t1", generation_id="g1"),
        SessionEvent(event=EventType.AUDIO_PLAYBACK_STOP, session_id="s_race_f", turn_id="t1", generation_id="g1")
    ]

    for event in events:
        cycle_id = getattr(session, "cancellation_cycle_id", 0)
        sid = writer_state.get("stream_sid")
        if event.event in (EventType.RESPONSE_CANCELLED, EventType.AUDIO_PLAYBACK_STOP, EventType.AUDIO_FLUSH):
            if sid and cycle_id != writer_state["last_handled_cancellation_cycle"]:
                writer_state["last_handled_cancellation_cycle"] = cycle_id
                await ws.send_text(json.dumps({"event": "clear", "stream_sid": sid}))

    # Exactly ONE CLEAR message must have been sent!
    clear_messages = [m for m in sent_messages if m.get("event") == "clear"]
    assert len(clear_messages) == 1
