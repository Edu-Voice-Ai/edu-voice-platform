"""SessionState and EphemeralTurnState maintaining strict session isolation and state transitions."""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time
from app.core.ids import generate_turn_id, generate_generation_id
from app.pipeline.cancellation import CancellationToken
from app.core.logging import get_logger
from app.audio.speaker_lock import AdaptiveSpeakerVoiceProfiler

logger = get_logger("session.state")


class TurnStateEnum(str, Enum):
    IDLE = "IDLE"
    GREETING = "GREETING"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    BARGE_IN = "BARGE_IN"
    INTERRUPTING = "INTERRUPTING"
    LISTENING_AFTER_BARGE_IN = "LISTENING_AFTER_BARGE_IN"
    INTERRUPTED = "INTERRUPTED"


class GenerationLifecycleState(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class ConversationFloor(str, Enum):
    IDLE = "IDLE"
    USER_SPEAKING = "USER_SPEAKING"
    AI_SPEAKING = "AI_SPEAKING"
    PROCESSING = "PROCESSING"


class GreetingStateEnum(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PLAYING = "PLAYING"
    COMPLETED = "COMPLETED"


@dataclass
class EphemeralTurnState:
    """Ephemeral state for an ongoing turn cycle."""
    turn_id: str = field(default_factory=generate_turn_id)
    generation_id: str = field(default_factory=generate_generation_id)
    state: TurnStateEnum = TurnStateEnum.IDLE
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    start_time_ms: float = field(default_factory=lambda: time.time() * 1000)
    user_audio_chunks: List[bytes] = field(default_factory=list)
    raw_transcript: str = ""
    generated_text: str = ""
    tts_audio_chunks_count: int = 0
    barge_in_handled: bool = False

    def cancel(self, reason: str = "Interrupted by user"):
        """Cancel this turn and transition state."""
        self.cancellation_token.cancel(reason)
        self.state = TurnStateEnum.INTERRUPTED


@dataclass
class SessionState:
    """Complete isolated state of an active voice session."""
    session_id: str
    organization_id: str
    agent_id: str
    call_id: Optional[str] = None
    language: str = "en-IN"
    preferred_language: Optional[str] = None
    language_selection_complete: bool = False
    institution_name: str = "Apex University"
    client_sample_rate: int = 16000
    created_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    is_active: bool = True
    user_has_floor: bool = False
    
    # Conversation History (List of dicts: {"role": "user"|"assistant"|"system"|"tool", "content": ...})
    messages: List[Dict[str, Any]] = field(default_factory=list)
    
    # Intelligence Data
    extracted_lead: Dict[str, Any] = field(default_factory=dict)
    handoff_requested: bool = False
    handoff_reason: Optional[str] = None
    call_summary: Optional[str] = None
    
    # Conversation & Lifecycle State
    conversation_state: str = "WAITING_FOR_LANGUAGE"
    waiting_for_consent: bool = False
    two_minute_permission_asked: bool = False
    consent_clarification_asked: bool = False
    consent_granted: Optional[bool] = None
    consecutive_empty_turns: int = 0
    is_greeting_playing: bool = False
    greeting_state: GreetingStateEnum = GreetingStateEnum.NOT_STARTED
    generation_states: Dict[str, GenerationLifecycleState] = field(default_factory=dict)
    cancelled_generation_ids: set[str] = field(default_factory=set)
    all_generation_ids: set[str] = field(default_factory=set)
    cancellation_cycle_id: int = 0
    barge_in_timestamp_ms: float = 0.0
    last_clear_timestamp_ms: float = 0.0
    last_old_audio_send_timestamp_ms: float = 0.0

    # Structured Input & Numeric Buffering State
    structured_input_mode: str = "NORMAL"
    numeric_segments: List[str] = field(default_factory=list)
    last_numeric_audio_at_ms: float = 0.0

    # Current active turn & response ownership tracking
    current_turn: EphemeralTurnState = field(default_factory=EphemeralTurnState)
    previous_turn_id: Optional[str] = None
    previous_generation_id: Optional[str] = None
    active_playback_generation_id: Optional[str] = None
    active_playback_turn_id: Optional[str] = None
    active_playback_language: Optional[str] = None
    is_bot_speaking: bool = False
    last_response_text: Optional[str] = None
    turn_count: int = 0
    playback_estimated_end_time_ms: float = 0.0

    # Adaptive Speaker Voice Profiler — locks onto primary caller's vocal identity on Turn 1
    speaker_profiler: AdaptiveSpeakerVoiceProfiler = field(default_factory=AdaptiveSpeakerVoiceProfiler)

    def extend_playback_deadline(self, duration_ms: float = 20.0):
        """Accumulate remaining physical playback time even when frames are queued faster than realtime."""
        now_ms = time.time() * 1000
        base = max(float(self.playback_estimated_end_time_ms or 0.0), now_ms)
        self.playback_estimated_end_time_ms = base + duration_ms

    def mark_playback_finished(self, force: bool = False):
        """Clear greeting/TTS playback flags when physical playout is done (or forced after telephony pacing)."""
        now_ms = time.time() * 1000
        self.is_greeting_playing = False
        self.active_playback_generation_id = None
        self.active_playback_turn_id = None
        self.active_playback_language = None
        if force or now_ms >= float(self.playback_estimated_end_time_ms or 0.0):
            self.is_bot_speaking = False
            self.playback_estimated_end_time_ms = 0.0
            self.user_has_floor = True
            if hasattr(self, "conversation_state"):
                self.conversation_state = "LISTENING"
            if self.current_turn and self.current_turn.state in (TurnStateEnum.SPEAKING, TurnStateEnum.IDLE):
                self.current_turn.state = TurnStateEnum.LISTENING

    def signal_playback_interrupt(self):
        """Wake the telephony writer immediately so it can send Exotel clear instead of finishing a pacing sleep."""
        import asyncio
        ev = getattr(self, "_playback_interrupt_event", None)
        if ev is None:
            ev = asyncio.Event()
            self._playback_interrupt_event = ev
        ev.set()

    def arm_playback_interrupt(self):
        """Reset the writer interrupt event at the start of a new TTS/greeting playout."""
        import asyncio
        ev = getattr(self, "_playback_interrupt_event", None)
        if ev is None:
            self._playback_interrupt_event = asyncio.Event()
        else:
            ev.clear()

    def playback_interrupt_event(self):
        return getattr(self, "_playback_interrupt_event", None)

    def set_generation_state(self, gen_id: str, state: GenerationLifecycleState):
        """Set generation lifecycle state with irreversibility for CANCELLED state."""
        current = self.generation_states.get(gen_id)
        if current == GenerationLifecycleState.CANCELLED:
            # Irreversible invariant: Once CANCELLED, a generation can NEVER return to ACTIVE or COMPLETED
            return
        self.generation_states[gen_id] = state
        if state == GenerationLifecycleState.CANCELLED:
            self.cancelled_generation_ids.add(gen_id)

    def get_generation_state(self, gen_id: Optional[str]) -> GenerationLifecycleState:
        """Get lifecycle state for a generation."""
        if not gen_id:
            return GenerationLifecycleState.CANCELLED
        if gen_id in self.cancelled_generation_ids:
            return GenerationLifecycleState.CANCELLED
        return self.generation_states.get(gen_id, GenerationLifecycleState.ACTIVE)

    @property
    def floor(self) -> ConversationFloor:
        """Authoritative single source of truth for who owns the audio floor."""
        if self.current_turn and self.current_turn.state in (TurnStateEnum.LISTENING, TurnStateEnum.LISTENING_AFTER_BARGE_IN):
            return ConversationFloor.USER_SPEAKING
        if getattr(self, "is_greeting_playing", False):
            return ConversationFloor.AI_SPEAKING
        if self.current_turn and self.current_turn.state == TurnStateEnum.SPEAKING:
            return ConversationFloor.AI_SPEAKING
        now_ms = time.time() * 1000
        if getattr(self, "is_bot_speaking", False) or (getattr(self, "active_playback_generation_id", None) and now_ms < self.playback_estimated_end_time_ms):
            return ConversationFloor.AI_SPEAKING
        if self.current_turn and self.current_turn.state == TurnStateEnum.PROCESSING:
            return ConversationFloor.PROCESSING
        return ConversationFloor.IDLE

    @property
    def is_assistant_speaking(self) -> bool:
        """Returns True if the assistant is actively speaking, generating, or audio is physically playing out on telephony buffer."""
        now_ms = time.time() * 1000
        estimated_end = float(getattr(self, "playback_estimated_end_time_ms", 0.0) or 0.0)
        return (
            bool(getattr(self, "is_bot_speaking", False))
            or bool(getattr(self, "is_greeting_playing", False))
            or (now_ms < estimated_end)
            or bool(getattr(self, "active_playback_generation_id", None))
        )

    def invalidate_active_generation(self, reason: str = "Interruption"):
        """Atomically invalidate active playback generation, record barge-in cutoff, and advance cancellation cycle."""
        now_ms = time.time() * 1000
        self.cancellation_cycle_id += 1
        self.barge_in_timestamp_ms = now_ms

        target_gids = set()
        if self.active_playback_generation_id:
            target_gids.add(self.active_playback_generation_id)
        if self.current_turn and self.current_turn.generation_id:
            target_gids.add(self.current_turn.generation_id)
        if self.previous_generation_id:
            target_gids.add(self.previous_generation_id)
        if hasattr(self, "all_generation_ids"):
            target_gids.update(self.all_generation_ids)

        for gid in target_gids:
            if gid:
                self.cancelled_generation_ids.add(gid)
                self.generation_states[gid] = GenerationLifecycleState.CANCELLED

        self.active_playback_generation_id = None
        self.active_playback_turn_id = None
        self.active_playback_language = None
        self.playback_estimated_end_time_ms = 0.0
        self.is_greeting_playing = False
        self.is_bot_speaking = False
        self.user_has_floor = True
        self.signal_playback_interrupt()

    def is_generation_cancelled(self, gen_id: Optional[str]) -> bool:
        """Check if a generation ID has been invalidated via barge-in."""
        if not gen_id:
            return False
        if gen_id in self.cancelled_generation_ids:
            return True
        return self.generation_states.get(gen_id) == GenerationLifecycleState.CANCELLED

    @property
    def conversation_style(self) -> str:
        """Returns the conversational style corresponding to the active preferred language."""
        active = self.preferred_language or self.language or "en-IN"
        return {"te-IN": "telugish", "hi-IN": "hinglish", "en-IN": "indian_english"}.get(active, "indian_english")

    @property
    def has_pending_numeric_input(self) -> bool:
        """Returns True if there are accumulated numeric segments waiting for continuation."""
        return len(self.numeric_segments) > 0

    def start_new_turn(self, reason: str = "New turn started", cancel_previous: bool = False) -> EphemeralTurnState:
        """Start a fresh turn with uncancelled token and increment turn counter."""
        old_turn_id = self.current_turn.turn_id if self.current_turn else "none"
        old_gen_id = self.current_turn.generation_id if self.current_turn else "none"
        old_state = self.current_turn.state if self.current_turn else TurnStateEnum.IDLE

        if self.current_turn:
            self.previous_turn_id = old_turn_id
            self.previous_generation_id = old_gen_id

        if cancel_previous and self.current_turn and not self.current_turn.cancellation_token.is_cancelled:
            self.current_turn.cancellation_token.cancel(reason)

        new_turn = EphemeralTurnState()
        new_turn.state = TurnStateEnum.LISTENING
        self.all_generation_ids.add(new_turn.generation_id)
        self.generation_states[new_turn.generation_id] = GenerationLifecycleState.ACTIVE
        self.current_turn = new_turn
        self.turn_count += 1

        logger.info(
            f"[STATE_TRANSITION] session_id={self.session_id} turn_id={new_turn.turn_id} gen_id={new_turn.generation_id} "
            f"old_turn={old_turn_id} old_state={old_state} new_state=LISTENING reason=\"{reason}\""
        )
        return self.current_turn

    def append_message(self, role: str, content: str, **kwargs):
        """Append message to conversation history."""
        msg = {"role": role, "content": content, "timestamp": time.time(), **kwargs}
        self.messages.append(msg)

    def close(self):
        """Close session and cancel active turn."""
        self.is_active = False
        if self.current_turn:
            self.current_turn.cancel("Session closed")
