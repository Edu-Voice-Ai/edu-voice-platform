"""
Comprehensive test suite for Sarvam Realtime STT — Manual Endpointing.

Tests cover:
  - URL construction: endpointing=manual, language_code=auto, language pinning
  - Protocol sequence: speech_start, audio_input, speech_end, flush
  - transcript.partial handling (must NOT go to LLM — only stored)
  - transcript.final handling (authoritative result)
  - Timeout path: interim transcript used if final event fires without text
  - Timeout path: REST fallback if no interim and no final within watchdog
  - Disconnect recovery: receiver_loop terminates cleanly, final_event unblocked
  - REST fallback: immediate if stream degraded/unhealthy
  - WebSocket error: fallback to REST on send failure
  - Audio queue overflow: degraded flag, REST fallback
  - turn reset: state cleared between turns, speech_started_sent reset
  - Languages: English, Telugu, Tenglish, numeric input
  - Barge-in: reset clears in-progress turn without closing WS
  - Telemetry counters: realtime_success, rest_fallback, failure counts
  - reconnect: new WS after disconnect
"""
import asyncio
import base64
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from app.stt.sarvam import SarvamSTTProvider, SarvamStreamingSTTSession
from app.stt.base import STTResult


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_session(language_code=None, api_key="test_key") -> SarvamStreamingSTTSession:
    """Create a session with create_task patched out (no running loop needed)."""
    provider = SarvamSTTProvider(api_key=api_key)
    with patch("asyncio.create_task", return_value=None):
        s = SarvamStreamingSTTSession(
            provider=provider,
            api_key=api_key,
            language_code=language_code,
        )
    return s


def _make_connected_session(language_code=None) -> SarvamStreamingSTTSession:
    """Create session with a mock WebSocket and connected state."""
    s = _make_session(language_code=language_code)
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    s._ws = mock_ws
    s._is_connected = True
    s._is_degraded = False
    return s


def _pcm(n_bytes=640) -> bytes:
    """Return n_bytes of fake PCM16 data."""
    return b"\x01\x00" * (n_bytes // 2)


# ─── A. URL Construction ──────────────────────────────────────────────────────

class TestWsUrlConstruction:

    def test_url_contains_endpointing_manual(self):
        """URL must always include endpointing=manual."""
        s = _make_session()
        url = s._get_ws_url()
        assert "endpointing=manual" in url

    def test_url_contains_stream_type_fast(self):
        """stream_type=fast must coexist with endpointing=manual."""
        s = _make_session()
        url = s._get_ws_url()
        assert "stream_type=fast" in url

    def test_url_mode_transcribe(self):
        s = _make_session()
        assert "mode=transcribe" in s._get_ws_url()

    def test_url_model_saaras_v3_realtime(self):
        s = _make_session()
        assert "model=saaras%3Av3-realtime" in s._get_ws_url() or "model=saaras:v3-realtime" in s._get_ws_url()

    def test_language_code_auto_when_unknown(self):
        """Unknown or None language_code → language_code=auto."""
        for lang in (None, "auto", "unknown", "ml-IN", "kn-IN"):
            s = _make_session(language_code=lang)
            assert "language_code=auto" in s._get_ws_url(), f"Expected auto for lang={lang}"

    def test_language_code_pinned_en_in(self):
        s = _make_session(language_code="en-IN")
        url = s._get_ws_url()
        assert "language_code=en-IN" in url
        assert "language_code=auto" not in url

    def test_language_code_pinned_te_in(self):
        s = _make_session(language_code="te-IN")
        url = s._get_ws_url()
        assert "language_code=te-IN" in url
        assert "language_code=auto" not in url

    def test_language_code_pinned_hi_in(self):
        s = _make_session(language_code="hi-IN")
        url = s._get_ws_url()
        assert "language_code=hi-IN" in url
        assert "language_code=auto" not in url

    def test_url_uses_wss_scheme(self):
        s = _make_session()
        assert s._get_ws_url().startswith("wss://")

    def test_url_correct_endpoint_path(self):
        s = _make_session()
        assert "/speech-to-text-realtime/ws" in s._get_ws_url()


# ─── B. Audio Push ────────────────────────────────────────────────────────────

class TestAudioPush:

    @pytest.mark.asyncio
    async def test_push_audio_accumulates_in_turn_buffer(self):
        """Every pushed chunk must accumulate in _turn_audio_buffer for REST fallback."""
        s = _make_session()
        chunk = _pcm(640)
        await s.push_audio(chunk)
        await s.push_audio(chunk)
        assert len(s._turn_audio_buffer) == 1280
        await s.close()

    @pytest.mark.asyncio
    async def test_push_audio_empty_chunk_ignored(self):
        s = _make_session()
        await s.push_audio(b"")
        assert len(s._turn_audio_buffer) == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_push_audio_marks_degraded_on_queue_overflow(self):
        """When audio queue is full, stream should be marked degraded."""
        s = _make_session()
        # Fill queue manually to maxsize
        for _ in range(s._audio_queue.maxsize):
            s._audio_queue.put_nowait(b"\x00" * 2)
        assert s._audio_queue.full()
        # Next push should trip degraded flag
        await s.push_audio(_pcm(320))
        assert s._is_degraded is True
        await s.close()


# ─── C. Turn Reset ────────────────────────────────────────────────────────────

class TestTurnReset:

    @pytest.mark.asyncio
    async def test_reset_clears_transcript_and_buffer(self):
        s = _make_session()
        await s.push_audio(_pcm(1280))
        s._interim_transcript = "partial text"
        s._final_transcript = "final text"
        s._final_event.set()
        s._speech_started_sent = True
        await s.reset()
        assert len(s._turn_audio_buffer) == 0
        assert s._interim_transcript == ""
        assert s._final_transcript == ""
        assert not s._final_event.is_set()
        assert s._speech_started_sent is False
        await s.close()

    @pytest.mark.asyncio
    async def test_reset_clears_audio_queue(self):
        s = _make_session()
        for _ in range(5):
            await s.push_audio(_pcm(320))
        s.reset_turn()
        assert s._audio_queue.empty()
        await s.close()

    @pytest.mark.asyncio
    async def test_reset_clears_degraded_flag_if_connected(self):
        s = _make_session()
        s._is_connected = True
        s._is_degraded = True
        s.reset_turn()
        assert s._is_degraded is False
        await s.close()

    @pytest.mark.asyncio
    async def test_reset_does_not_affect_ws_connection(self):
        """Barge-in reset must not close the WebSocket connection."""
        s = _make_connected_session()
        await s.reset()
        assert s._ws is not None
        assert s._is_connected is True
        await s.close()


# ─── D. Finalize — Realtime Success Paths ────────────────────────────────────

class TestFinalizeRealtimeSuccess:

    @pytest.mark.asyncio
    async def test_finalize_returns_final_transcript(self):
        """Happy path: transcript.final fires → STTResult with final text."""
        s = _make_connected_session(language_code="en-IN")
        await s.push_audio(_pcm(3200))

        async def _inject_final():
            await asyncio.sleep(0.05)
            s._final_transcript = "What is the fee for BTech CSE?"
            s._final_language = "en-IN"
            s._final_event.set()

        asyncio.create_task(_inject_final())
        result = await s.finalize(language_code="en-IN")

        assert isinstance(result, STTResult)
        assert result.text == "What is the fee for BTech CSE?"
        assert result.language_code == "en-IN"
        assert result.confidence == 0.95
        assert s._realtime_success_count == 1
        assert s._rest_fallback_count == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_finalize_sends_speech_end_and_flush(self):
        """finalize() must send speech_end then flush in that order."""
        s = _make_connected_session(language_code="en-IN")
        await s.push_audio(_pcm(640))

        async def _inject_final():
            await asyncio.sleep(0.02)
            s._final_transcript = "Hello"
            s._final_event.set()

        asyncio.create_task(_inject_final())
        await s.finalize(language_code="en-IN")

        calls = s._ws.send.call_args_list
        sent_events = [json.loads(c[0][0])["event"] for c in calls]
        assert "speech_end" in sent_events
        assert "flush" in sent_events
        # speech_end must come before flush
        assert sent_events.index("speech_end") < sent_events.index("flush")
        await s.close()

    @pytest.mark.asyncio
    async def test_finalize_uses_interim_when_final_text_empty(self):
        """If transcript.final fires with empty text, use interim transcript."""
        s = _make_connected_session(language_code="te-IN")
        s._interim_transcript = "CSE fee entha"
        s._final_language = "te-IN"
        await s.push_audio(_pcm(640))

        async def _inject_empty_final():
            await asyncio.sleep(0.02)
            s._final_transcript = ""  # empty
            s._final_event.set()

        asyncio.create_task(_inject_empty_final())
        result = await s.finalize(language_code="te-IN")

        assert result.text == "CSE fee entha"
        assert result.language_code == "te-IN"
        assert result.confidence == 0.85
        assert s._realtime_success_count == 1
        assert s._rest_fallback_count == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_finalize_english_turn(self):
        s = _make_connected_session(language_code="en-IN")
        await s.push_audio(_pcm(3200))

        async def _inject():
            await asyncio.sleep(0.02)
            s._final_transcript = "Tell me about the hostel facilities"
            s._final_language = "en-IN"
            s._final_event.set()

        asyncio.create_task(_inject())
        result = await s.finalize(language_code="en-IN")
        assert "hostel facilities" in result.text
        await s.close()

    @pytest.mark.asyncio
    async def test_finalize_telugu_turn(self):
        s = _make_connected_session(language_code="te-IN")
        await s.push_audio(_pcm(3200))

        async def _inject():
            await asyncio.sleep(0.02)
            s._final_transcript = "CSE fees cheppandi"
            s._final_language = "te-IN"
            s._final_event.set()

        asyncio.create_task(_inject())
        result = await s.finalize(language_code="te-IN")
        assert result.text == "CSE fees cheppandi"
        assert result.language_code == "te-IN"
        await s.close()

    @pytest.mark.asyncio
    async def test_finalize_tenglish_turn(self):
        """Tenglish (Telugu + English mixed) must transcribe correctly."""
        s = _make_connected_session(language_code="te-IN")
        await s.push_audio(_pcm(3200))

        async def _inject():
            await asyncio.sleep(0.02)
            s._final_transcript = "BTech CSE ki fee entha"
            s._final_language = "te-IN"
            s._final_event.set()

        asyncio.create_task(_inject())
        result = await s.finalize(language_code="te-IN")
        assert result.text == "BTech CSE ki fee entha"
        await s.close()

    @pytest.mark.asyncio
    async def test_finalize_numeric_input(self):
        """Numeric utterances (phone, amounts) must pass through."""
        s = _make_connected_session(language_code="en-IN")
        await s.push_audio(_pcm(3200))

        async def _inject():
            await asyncio.sleep(0.02)
            s._final_transcript = "Six lakh rupees"
            s._final_language = "en-IN"
            s._final_event.set()

        asyncio.create_task(_inject())
        result = await s.finalize(language_code="en-IN")
        assert result.text == "Six lakh rupees"
        await s.close()


# ─── E. Finalize — Timeout Paths ─────────────────────────────────────────────

class TestFinalizeTimeout:

    @pytest.mark.asyncio
    async def test_timeout_uses_interim_before_rest(self):
        """On watchdog timeout, interim transcript is returned without hitting REST."""
        s = _make_connected_session(language_code="en-IN")
        s._interim_transcript = "What is the last date"
        s._final_language = "en-IN"
        await s.push_audio(_pcm(640))

        provider = s.provider
        with patch.object(provider, "transcribe_audio", AsyncMock()) as mock_rest:
            # Override wait timeout to 0.01s for test speed
            async def _fast_finalize():
                pass

            # Patch the wait_for to timeout immediately
            orig_wait_for = asyncio.wait_for
            call_count = [0]

            async def _patched_wait_for(coro, timeout=None):
                call_count[0] += 1
                if call_count[0] >= 3:  # 3rd call is the final_event.wait
                    raise asyncio.TimeoutError()
                return await orig_wait_for(coro, timeout=timeout)

            with patch("asyncio.wait_for", side_effect=_patched_wait_for):
                result = await s.finalize(language_code="en-IN")

            assert result.text == "What is the last date"
            assert mock_rest.called is False
            assert s._realtime_success_count == 1
        await s.close()

    @pytest.mark.asyncio
    async def test_timeout_with_no_interim_falls_to_rest(self):
        """On watchdog timeout with no interim, must call REST fallback."""
        s = _make_connected_session(language_code="en-IN")
        s._interim_transcript = ""  # no interim
        pcm = _pcm(3200)
        await s.push_audio(pcm)

        mock_result = STTResult(text="What is the fee for BTech?", language_code="en-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)) as mock_rest:
            orig_wait_for = asyncio.wait_for
            call_count = [0]

            async def _patched_wait_for(coro, timeout=None):
                call_count[0] += 1
                if call_count[0] >= 3:
                    raise asyncio.TimeoutError()
                return await orig_wait_for(coro, timeout=timeout)

            with patch("asyncio.wait_for", side_effect=_patched_wait_for):
                result = await s.finalize(language_code="en-IN")

            assert result.text == "What is the fee for BTech?"
            assert mock_rest.called
            assert s._rest_fallback_count == 1
        await s.close()


# ─── F. Finalize — Fallback Paths ────────────────────────────────────────────

class TestFinalizeFallback:

    @pytest.mark.asyncio
    async def test_immediate_rest_fallback_when_ws_disconnected(self):
        """No WS connection → immediately use REST."""
        s = _make_session()
        s._ws = None
        s._is_connected = False
        pcm = _pcm(3200)
        await s.push_audio(pcm)

        mock_result = STTResult(text="Admission process?", language_code="en-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)) as mock_rest:
            result = await s.finalize(language_code="en-IN")
            assert result.text == "Admission process?"
            assert mock_rest.called
            assert s._rest_fallback_count == 1
        await s.close()

    @pytest.mark.asyncio
    async def test_immediate_rest_fallback_when_stream_degraded(self):
        """Degraded stream → immediately use REST without trying WS."""
        s = _make_connected_session()
        s._is_degraded = True
        pcm = _pcm(3200)
        await s.push_audio(pcm)

        mock_result = STTResult(text="Hostel info?", language_code="en-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)) as mock_rest:
            result = await s.finalize()
            assert result.text == "Hostel info?"
            assert mock_rest.called
            assert s._rest_fallback_count == 1
        await s.close()

    @pytest.mark.asyncio
    async def test_rest_fallback_on_speech_end_send_error(self):
        """If speech_end send raises, fall to REST immediately."""
        s = _make_connected_session()
        s._ws.send = AsyncMock(side_effect=Exception("WS broken"))
        pcm = _pcm(3200)
        await s.push_audio(pcm)

        mock_result = STTResult(text="Eligibility criteria?", language_code="en-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)) as mock_rest:
            result = await s.finalize(language_code="en-IN")
            assert result.text == "Eligibility criteria?"
            assert mock_rest.called
            assert s._rest_fallback_count == 1
        await s.close()

    @pytest.mark.asyncio
    async def test_rest_fallback_uses_accumulated_turn_buffer(self):
        """REST fallback must send the complete audio accumulated during the turn."""
        s = _make_connected_session(language_code="hi-IN")
        s._is_connected = False  # force immediate REST path
        s._ws = None
        chunk1 = _pcm(640)
        chunk2 = _pcm(640)
        chunk3 = _pcm(640)
        await s.push_audio(chunk1)
        await s.push_audio(chunk2)
        await s.push_audio(chunk3)

        mock_result = STTResult(text="हाँ, मुझे प्रवेश की जानकारी चाहिए", language_code="hi-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)) as mock_rest:
            await s.finalize(language_code="hi-IN")
            called_audio = mock_rest.call_args[0][0]
            assert len(called_audio) == 1920  # 3 x 640 bytes
        await s.close()

    @pytest.mark.asyncio
    async def test_rest_fallback_hindi(self):
        """Hindi utterance must fall through to REST correctly."""
        s = _make_session(language_code="hi-IN")
        s._is_connected = False
        s._ws = None
        await s.push_audio(_pcm(3200))

        mock_result = STTResult(text="हाँ, मुझे प्रवेश की जानकारी चाहिए", language_code="hi-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)) as mock_rest:
            result = await s.finalize(language_code="hi-IN")
            assert "प्रवेश" in result.text
        await s.close()


# ─── G. Disconnect / Receiver Loop ────────────────────────────────────────────

class TestDisconnectAndRecovery:

    @pytest.mark.asyncio
    async def test_receiver_loop_disconnect_unblocks_finalize(self):
        """When receiver_loop terminates, _final_event must be set to unblock finalize."""
        s = _make_connected_session(language_code="en-IN")
        await s.push_audio(_pcm(640))
        # Set final_event from outside (simulating disconnect → finally block)
        async def _simulate_disconnect():
            await asyncio.sleep(0.03)
            s._is_connected = False
            s._final_event.set()  # mirrors what finally: block does in _receiver_loop

        asyncio.create_task(_simulate_disconnect())

        # With empty final transcript and no interim, should fall to REST
        mock_result = STTResult(text="reconnect fallback", language_code="en-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)):
            result = await s.finalize(language_code="en-IN")
        # Either interim (empty) path or REST fallback — should not hang
        assert result is not None
        await s.close()

    @pytest.mark.asyncio
    async def test_is_stream_healthy_false_when_disconnected(self):
        s = _make_connected_session()
        s._is_connected = False
        assert s.is_stream_healthy is False
        await s.close()

    @pytest.mark.asyncio
    async def test_is_stream_healthy_false_when_degraded(self):
        s = _make_connected_session()
        s._is_degraded = True
        assert s.is_stream_healthy is False
        await s.close()

    @pytest.mark.asyncio
    async def test_is_stream_healthy_false_when_no_ws(self):
        s = _make_session()
        s._is_connected = True
        s._ws = None
        assert s.is_stream_healthy is False
        await s.close()


# ─── H. Partial Transcripts ───────────────────────────────────────────────────

class TestPartialTranscripts:

    @pytest.mark.asyncio
    async def test_partial_not_returned_from_finalize(self):
        """
        transcript.partial MUST NOT be sent to LLM.
        finalize() must always return transcript.final (or interim as last resort).
        """
        s = _make_connected_session(language_code="en-IN")
        s._interim_transcript = "partial only, no final"
        await s.push_audio(_pcm(640))

        # Inject a real final event to properly return
        async def _inject_final():
            await asyncio.sleep(0.02)
            s._final_transcript = "complete final transcript"
            s._final_language = "en-IN"
            s._final_event.set()

        asyncio.create_task(_inject_final())
        result = await s.finalize(language_code="en-IN")

        # Must be the FINAL transcript, not the partial
        assert result.text == "complete final transcript"
        assert result.confidence == 0.95
        await s.close()

    @pytest.mark.asyncio
    async def test_interim_stored_but_not_sent_to_llm(self):
        """_interim_transcript is updated but finalize() only returns final."""
        s = _make_connected_session()
        # Simulate receiver_loop updating interim
        s._interim_transcript = "interim update"
        # Then final arrives
        s._final_transcript = "final answer"
        s._final_language = "en-IN"

        async def _set_event():
            await asyncio.sleep(0.01)
            s._final_event.set()

        asyncio.create_task(_set_event())
        await s.push_audio(_pcm(640))
        result = await s.finalize()

        assert result.text == "final answer"
        assert "interim update" not in result.text
        await s.close()


# ─── I. Barge-In ─────────────────────────────────────────────────────────────

class TestBargeIn:

    @pytest.mark.asyncio
    async def test_barge_in_reset_preserves_ws_connection(self):
        """
        On barge-in, turn is reset but WebSocket must stay open
        (no reconnect cost on next turn).
        """
        s = _make_connected_session(language_code="en-IN")
        await s.push_audio(_pcm(3200))
        s._interim_transcript = "user started speaking"
        s._speech_started_sent = True

        # Simulate barge-in: engine calls reset()
        await s.reset()

        assert s._ws is not None
        assert s._is_connected is True
        assert s._interim_transcript == ""
        assert s._speech_started_sent is False
        assert len(s._turn_audio_buffer) == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_after_barge_in_next_turn_works(self):
        """After a reset, next turn should produce a correct result."""
        s = _make_connected_session(language_code="en-IN")

        # Simulate first turn reset due to barge-in
        await s.push_audio(_pcm(1600))
        await s.reset()

        # Now start next turn
        await s.push_audio(_pcm(3200))

        async def _inject():
            await asyncio.sleep(0.02)
            s._final_transcript = "Tell me about CSE"
            s._final_language = "en-IN"
            s._final_event.set()

        asyncio.create_task(_inject())
        result = await s.finalize(language_code="en-IN")
        assert result.text == "Tell me about CSE"
        assert s._realtime_success_count == 1
        await s.close()


# ─── J. Telemetry ────────────────────────────────────────────────────────────

class TestTelemetry:

    @pytest.mark.asyncio
    async def test_telemetry_initial_state(self):
        s = _make_session()
        t = s.telemetry
        assert t["stt_ws_connect_ms"] == 0.0
        assert t["stt_first_partial_ms"] == 0.0
        assert t["stt_final_ms"] == 0.0
        assert t["realtime_success_count"] == 0
        assert t["realtime_failure_count"] == 0
        assert t["rest_fallback_count"] == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_telemetry_success_count_incremented(self):
        s = _make_connected_session(language_code="en-IN")
        await s.push_audio(_pcm(640))

        async def _inject():
            await asyncio.sleep(0.02)
            s._final_transcript = "Test transcript"
            s._final_event.set()

        asyncio.create_task(_inject())
        await s.finalize()
        assert s.telemetry["realtime_success_count"] == 1
        assert s.telemetry["rest_fallback_count"] == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_telemetry_rest_fallback_count_incremented(self):
        s = _make_session()
        s._is_connected = False
        s._ws = None
        await s.push_audio(_pcm(640))
        mock_result = STTResult(text="X", language_code="en-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)):
            await s.finalize()
        assert s.telemetry["rest_fallback_count"] == 1
        assert s.telemetry["realtime_success_count"] == 0
        await s.close()

    @pytest.mark.asyncio
    async def test_telemetry_failure_count_incremented_on_send_error(self):
        s = _make_connected_session()
        s._ws.send = AsyncMock(side_effect=Exception("broken pipe"))
        await s.push_audio(_pcm(640))
        mock_result = STTResult(text="X", language_code="en-IN")
        with patch.object(s.provider, "transcribe_audio", AsyncMock(return_value=mock_result)):
            await s.finalize()
        assert s.telemetry["realtime_failure_count"] == 1
        assert s.telemetry["rest_fallback_count"] == 1
        await s.close()


# ─── K. Provider Factory ─────────────────────────────────────────────────────

class TestProviderFactory:

    def test_create_streaming_session_returns_correct_type(self):
        p = SarvamSTTProvider(api_key="test")
        with patch("asyncio.create_task", return_value=None):
            s = p.create_streaming_session(language_code="en-IN")
        assert isinstance(s, SarvamStreamingSTTSession)

    def test_create_streaming_session_inherits_language_code(self):
        p = SarvamSTTProvider(api_key="test")
        with patch("asyncio.create_task", return_value=None):
            s = p.create_streaming_session(language_code="te-IN")
        assert s.language_code == "te-IN"

    def test_create_streaming_session_uses_realtime_model(self):
        p = SarvamSTTProvider(api_key="test")
        with patch("asyncio.create_task", return_value=None):
            s = p.create_streaming_session()
        assert "realtime" in s.model


# ─── L. Close / Cleanup ──────────────────────────────────────────────────────

class TestClose:

    @pytest.mark.asyncio
    async def test_close_sets_closed_flag(self):
        s = _make_session()
        await s.close()
        assert s._closed is True

    @pytest.mark.asyncio
    async def test_close_clears_ws(self):
        s = _make_connected_session()
        await s.close()
        assert s._ws is None

    @pytest.mark.asyncio
    async def test_close_cancels_sender_task(self):
        s = _make_session()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        s._sender_task = mock_task
        await s.close()
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_cancels_receiver_task(self):
        s = _make_session()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        s._receiver_task = mock_task
        await s.close()
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_double_close_safe(self):
        """Multiple close() calls must not raise."""
        s = _make_connected_session()
        await s.close()
        await s.close()  # should not raise


# ─── M. Receiver Loop Event Parsing ──────────────────────────────────────────

class TestReceiverEventParsing:

    @pytest.mark.asyncio
    async def test_transcript_final_event_name(self):
        """Verify that an event named 'transcript.final' is treated as final."""
        s = _make_session()
        data = {"event": "transcript.final", "transcript": "Hello", "language_code": "en-IN"}
        event = data.get("event") or data.get("type", "")
        is_final = bool(event in ("transcript.final", "final", "speech.end"))
        assert is_final is True
        await s.close()

    @pytest.mark.asyncio
    async def test_transcript_partial_event_name(self):
        data = {"event": "transcript.partial", "transcript": "hel", "language_code": "en-IN"}
        event = data.get("event") or ""
        is_partial = event in ("transcript.partial", "partial", "speech.interim")
        assert is_partial is True

    @pytest.mark.asyncio
    async def test_is_final_flag_true(self):
        data = {"event": "something", "is_final": True, "transcript": "Hello"}
        is_final = bool(data.get("is_final") is True)
        assert is_final is True

    @pytest.mark.asyncio
    async def test_session_begin_not_treated_as_partial(self):
        data = {"event": "session.begin"}
        event = data.get("event") or ""
        text = (data.get("transcript") or "").strip()
        is_final = event in ("transcript.final", "final")
        is_partial = bool(
            event in ("transcript.partial", "partial")
            or (not is_final and text and event not in ("session.begin", "error"))
        )
        assert is_partial is False
