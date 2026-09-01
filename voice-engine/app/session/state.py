"""SessionState and EphemeralTurnState maintaining strict session isolation and state transitions."""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time
from app.core.ids import generate_turn_id, generate_generation_id
from app.pipeline.cancellation import CancellationToken
from app.core.logging import get_logger

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
    is_greeting_playing: bool = False
    greeting_state: GreetingStateEnum = GreetingStateEnum.NOT_STARTED
    cancelled_generation_ids: set[str] = field(default_factory=set)
    all_generation_ids: set[str] = field(default_factory=set)

    # Structured Input & Numeric Buffering State
    structured_input_mode: str = "NORMAL"
    numeric_segments: List[str] = field(default_factory=list)
    last_numeric_audio_at_ms: float = 0.0

    # Current active turn & response ownership tracking
    current_turn: EphemeralTurnState = field(default_factory=EphemeralTurnState)
    previous_turn_id: Optional[str] = None
    previous_generation_id: Optional[str] = None
    last_response_text: Optional[str] = None
    turn_count: int = 0
    playback_estimated_end_time_ms: float = 0.0

    @property
    def is_assistant_speaking(self) -> bool:
        """Returns True if the assistant is actively speaking or audio is physically playing out on telephony buffer."""
        if getattr(self, "is_greeting_playing", False):
            return True
        if self.current_turn and self.current_turn.state in (TurnStateEnum.SPEAKING, TurnStateEnum.PROCESSING):
            return True
        if self.current_turn and self.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN:
            return False
        now_ms = time.time() * 1000
        return now_ms < self.playback_estimated_end_time_ms

    def is_generation_cancelled(self, gen_id: Optional[str]) -> bool:
        """Check if a generation ID has been invalidated via barge-in."""
        if not gen_id:
            return False
        return gen_id in self.cancelled_generation_ids

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
