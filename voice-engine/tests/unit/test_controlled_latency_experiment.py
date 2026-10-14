"""Unit tests for Controlled Voice Engine Latency Experiment.
Verifies Baseline (VAD 350ms, First-Chunk 60 chars) vs Experiment (VAD 300ms, First-Chunk 45 chars).
"""
import pytest
import asyncio
from unittest.mock import AsyncMock
from app.core.config import Settings
from app.pipeline.turn_manager import TurnManager
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.tts.sarvam import SarvamTTSProvider
from app.tts.text_normalizer import SpeechTextNormalizer
from app.pipeline.cancellation import CancellationToken


class TestControlledLatencyExperimentConfiguration:
    """Verifies feature flag defaults and dynamic threshold computation."""

    def test_default_is_baseline(self):
        s = Settings(VOICE_LATENCY_EXPERIMENT=False)
        assert s.voice_latency_experiment is False
        assert s.effective_conversational_silence_ms == 350
        assert s.effective_first_chunk_min_chars == 60

    def test_experimental_flag_enables_300ms_and_45chars(self):
        s = Settings(VOICE_LATENCY_EXPERIMENT=True)
        assert s.voice_latency_experiment is True
        assert s.effective_conversational_silence_ms == 300
        assert s.effective_first_chunk_min_chars == 45

    def test_individual_overrides_respected(self):
        s = Settings(
            VOICE_LATENCY_EXPERIMENT=False,
            NORMAL_SILENCE_MS=320,
            TTS_FIRST_CHUNK_MIN_CHARS=50
        )
        assert s.effective_conversational_silence_ms == 320
        assert s.effective_first_chunk_min_chars == 50


class TestVADConversationalThresholds:
    """Verifies TurnManager endpointing for 350ms baseline vs 300ms experiment."""

    def test_baseline_350ms_endpointing(self):
        session = SessionState(session_id="test_baseline", organization_id="org_1", agent_id="agent_1")
        queues = PipelineQueueBundle()
        tm = TurnManager(
            session=session,
            queues=queues,
            min_silence_duration_ms=350,
            normal_silence_ms=350,
            short_utterance_silence_ms=350,
            structured_input_silence_ms=1200
        )
        # Normal conversational turn
        tm._total_turn_speech_ms = 800.0
        assert tm.effective_silence_duration_ms == 350.0

    def test_experiment_300ms_endpointing(self):
        session = SessionState(session_id="test_exp", organization_id="org_1", agent_id="agent_1")
        queues = PipelineQueueBundle()
        tm = TurnManager(
            session=session,
            queues=queues,
            min_silence_duration_ms=300,
            normal_silence_ms=300,
            short_utterance_silence_ms=300,
            structured_input_silence_ms=1200
        )
        # Normal conversational turn
        tm._total_turn_speech_ms = 800.0
        assert tm.effective_silence_duration_ms == 300.0

    def test_structured_numeric_mode_strictly_retains_1200ms_in_both_modes(self):
        session = SessionState(session_id="test_numeric", organization_id="org_1", agent_id="agent_1")
        session.structured_input_mode = "PHONE_NUMBER"
        queues = PipelineQueueBundle()

        # In baseline
        tm_base = TurnManager(session=session, queues=queues, normal_silence_ms=350, structured_input_silence_ms=1200)
        assert tm_base.effective_silence_duration_ms == 1200.0

        # In experiment
        tm_exp = TurnManager(session=session, queues=queues, normal_silence_ms=300, structured_input_silence_ms=1200)
        assert tm_exp.effective_silence_duration_ms == 1200.0

    def test_post_barge_in_recovery_strictly_retains_400ms_in_both_modes(self):
        session = SessionState(session_id="test_barge_in", organization_id="org_1", agent_id="agent_1")
        turn = session.start_new_turn("test")
        turn.state = TurnStateEnum.LISTENING_AFTER_BARGE_IN
        queues = PipelineQueueBundle()

        # In baseline
        tm_base = TurnManager(session=session, queues=queues, normal_silence_ms=350)
        assert tm_base.effective_silence_duration_ms == 400.0

        # In experiment
        tm_exp = TurnManager(session=session, queues=queues, normal_silence_ms=300)
        assert tm_exp.effective_silence_duration_ms == 400.0


class TestFirstClauseChunkingThresholds:
    """Verifies 60-character baseline vs 45-character experimental dispatch."""

    @pytest.mark.asyncio
    async def test_baseline_60_char_threshold_accumulates_under_60(self):
        provider = SarvamTTSProvider(api_key="mock", first_chunk_min_chars=60)
        provider.synthesize_text = AsyncMock(return_value=b"\x00" * 3200)

        # Clause of 48 chars with terminal period
        text_clause = "The total BTech CSE tuition fee is very nominal."
        assert len(text_clause) == 48

        async def token_stream():
            yield text_clause

        chunks = []
        async for chunk in provider.stream_synthesize(token_stream()):
            chunks.append(chunk)

        # In baseline (60 chars), 48 chars was held until EOF and synthesized as 1 chunk
        assert provider.synthesize_text.call_count == 1
        call_text = provider.synthesize_text.call_args_list[0][0][0]
        assert call_text == text_clause

    @pytest.mark.asyncio
    async def test_experiment_45_char_threshold_dispatches_clause_at_48_chars(self):
        provider = SarvamTTSProvider(api_key="mock", first_chunk_min_chars=45)
        provider.synthesize_text = AsyncMock(return_value=b"\x00" * 3200)

        # Two clauses: first is 48 chars, second is 50 chars
        clause_1 = "The total BTech CSE tuition fee is very nominal."
        clause_2 = " Would you like to know about our scholarship?"
        assert len(clause_1) == 48

        async def token_stream():
            yield clause_1
            # Brief pause simulating LLM streaming
            await asyncio.sleep(0.01)
            yield clause_2

        chunks = []
        async for chunk in provider.stream_synthesize(token_stream()):
            chunks.append(chunk)

        # Clause 1 (48 chars >= 45) was dispatched immediately without waiting for Clause 2!
        assert provider.synthesize_text.call_count == 2
        first_call_text = provider.synthesize_text.call_args_list[0][0][0]
        assert first_call_text == clause_1

    def test_sentence_terminal_punctuation_strictly_required_no_comma_split(self):
        """Verifies comma does NOT cause a TTS split in both baseline and experimental modes."""
        text_with_comma_no_period = "CSE yearly fee 1,50,000 rupees ఉంటుంది, సో నాలుగు సంవత్సరాలకు total 6,00,000 rupees అవుతుంది"
        # Without terminal punctuation [.!?।\n], it must return None
        chunk, remaining = SpeechTextNormalizer.extract_safe_chunk(text_with_comma_no_period, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True)
        assert chunk is None
        assert remaining == text_with_comma_no_period

        # When terminal period IS present, the whole sentence is kept intact as ONE chunk, not split at comma
        text_with_period = text_with_comma_no_period + "."
        chunk, remaining = SpeechTextNormalizer.extract_safe_chunk(text_with_period, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True)
        assert chunk == text_with_period
        assert remaining == ""

    def test_sentence_terminal_punctuation_strictly_required_no_semicolon_split(self):
        """Verifies semicolon does NOT cause a TTS split."""
        text_with_semi_no_period = "Admissions are currently open; please visit the administrative office"
        chunk, remaining = SpeechTextNormalizer.extract_safe_chunk(text_with_semi_no_period, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True)
        assert chunk is None
        assert remaining == text_with_semi_no_period

        text_with_period = text_with_semi_no_period + "."
        chunk, remaining = SpeechTextNormalizer.extract_safe_chunk(text_with_period, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True)
        assert chunk == text_with_period
        assert remaining == ""

    def test_short_greetings_remain_naturally_grouped(self):
        """Verifies short utterances (< 45 chars) are not broken."""
        greeting = "నమస్కారం, నేను కార్తీక్ ని."
        assert len(greeting) < 45
        # Under 45 chars, stream_synthesize segmenter accumulates until EOF
        chunk, remaining = SpeechTextNormalizer.extract_safe_chunk(greeting, min_chars=35, max_chars=180, is_eof=True, is_first_chunk=True)
        assert chunk == greeting
        assert remaining == ""

    @pytest.mark.asyncio
    async def test_barge_in_cancellation_during_synthesis(self):
        """Verifies cancellation_token immediately halts generation without stale audio."""
        provider = SarvamTTSProvider(api_key="mock", first_chunk_min_chars=45)
        provider.synthesize_text = AsyncMock(return_value=b"\x00" * 3200)

        token = CancellationToken()
        token.cancel()

        async def token_stream():
            yield "Hello, how can I help you today?"

        chunks = []
        async for chunk in provider.stream_synthesize(token_stream(), cancellation_token=token):
            chunks.append(chunk)

        assert len(chunks) == 0
        assert provider.synthesize_text.call_count == 0
