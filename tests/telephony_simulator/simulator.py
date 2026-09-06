"""Local Telephony Simulator Core Harness (TEST ONLY).

Coordinates full simulated telephony call lifecycles, WebSocket audio exchange,
DTMF keypresses, barge-in interruption events, and concurrent call sessions.

NOTE: This is a local development and CI test harness.
It does NOT connect to external telecom networks or real carrier endpoints.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from backend.app.services.telephony.events import (
    NormalizedTelephonyEvent,
    TelephonyEventType,
)
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    RealtimeVoiceSession,
)
from backend.app.services.telephony.session_manager import (
    RealtimeSessionManager,
    get_realtime_session_manager,
)
from tests.telephony_simulator.synthetic_audio import (
    SyntheticAudioFrame,
    SyntheticAudioGenerator,
)
from tests.telephony_simulator.webhook_generator import SimulatedWebhookClient


@dataclass
class SimulatedCallResult:
    """Summary record of a completed simulated telephony call."""

    call_sid: str
    session_id: str
    tenant_id: str
    organization_id: str
    agent_id: str
    inbound_frames_sent: int
    outbound_frames_received: int
    dtmf_events_sent: int
    interruptions_triggered: int
    final_connection_state: ConnectionState
    success: bool
    details: dict[str, Any] = field(default_factory=dict)


class SimulatedTelephonyCall:
    """Represents a single end-to-end simulated phone call session."""

    def __init__(
        self,
        call_sid: str,
        session_id: str,
        from_number: str = "+919876543210",
        to_number: str = "+911140001234",
        organization_id: str = "org_sim_school_01",
        tenant_id: str = "tenant_sim_01",
        agent_id: str = "agent_sim_admission_01",
    ) -> None:
        self.call_sid: str = call_sid
        self.session_id: str = session_id
        self.from_number: str = from_number
        self.to_number: str = to_number
        self.organization_id: str = organization_id
        self.tenant_id: str = tenant_id
        self.agent_id: str = agent_id

        self.audio_generator: SyntheticAudioGenerator = SyntheticAudioGenerator()
        self.inbound_frames_sent: int = 0
        self.outbound_frames_received: int = 0
        self.dtmf_sent: list[str] = []
        self.interruptions_triggered: int = 0

    async def execute_full_lifecycle(
        self,
        session_manager: RealtimeSessionManager,
        num_inbound_frames: int = 5,
        simulate_barge_in: bool = True,
        dtmf_digits: list[str] | None = None,
    ) -> SimulatedCallResult:
        """Execute a complete simulated call session against the voice gateway."""
        digits = dtmf_digits or ["1"]

        # 1. Create session in session manager
        session: RealtimeVoiceSession = await session_manager.create_session(
            session_id=self.session_id,
            call_sid=self.call_sid,
            organization_id=self.organization_id,
            agent_id=self.agent_id,
        )

        # 2. Set connection state to connected
        session.connection_state = ConnectionState.CONNECTED

        # 3. Simulate START / CALL_CONNECTED events
        start_event = NormalizedTelephonyEvent(
            event_type=TelephonyEventType.START,
            call_id=self.call_sid,
            session_id=self.session_id,
            from_number=self.from_number,
            to_number=self.to_number,
        )
        assert start_event.event_type == TelephonyEventType.START

        # 4. Stream initial synthetic caller audio frames into inbound queue
        for frame in self.audio_generator.generate_frame_stream(
            count=num_inbound_frames
        ):
            audio_frame = AudioFrame(
                data=frame.raw_bytes,
                sequence_number=frame.sequence,
                timestamp_ms=frame.timestamp_ms,
            )
            success = await session.push_inbound_frame(audio_frame)
            if success:
                self.inbound_frames_sent += 1

        # 5. Populate outbound audio queue (simulating Agent TTS response)
        for seq in range(1, 4):
            agent_frame: SyntheticAudioFrame = (
                self.audio_generator.generate_agent_audio_frame(sequence=seq)
            )
            agent_audio_frame = AudioFrame(
                data=agent_frame.raw_bytes,
                sequence_number=agent_frame.sequence,
                timestamp_ms=agent_frame.timestamp_ms,
            )
            await session.push_outbound_frame(agent_audio_frame)

        # 6. Simulate DTMF Keypress
        for digit in digits:
            dtmf_event = NormalizedTelephonyEvent(
                event_type=TelephonyEventType.DTMF,
                call_id=self.call_sid,
                session_id=self.session_id,
                dtmf_digit=digit,
            )
            self.dtmf_sent.append(digit)
            assert dtmf_event.dtmf_digit == digit

        # 7. Simulate Barge-In / Interruption (if requested)
        if simulate_barge_in:
            self.interruptions_triggered += 1
            # Outbound queue should have items before interrupt
            initial_outbound_size = session.outbound_audio_queue.qsize()
            drained_count = session.trigger_interruption()
            # Interruption should have drained the outbound queue
            drained_outbound_size = session.outbound_audio_queue.qsize()
            assert drained_outbound_size == 0, (
                f"Expected drained queue, found {drained_outbound_size} (was {initial_outbound_size})"
            )
            assert drained_count >= 1

            # Caller resumes speaking post-interruption
            post_frame = self.audio_generator.generate_caller_audio_frame(
                sequence=100, tag="post_interrupt"
            )
            post_audio_frame = AudioFrame(
                data=post_frame.raw_bytes,
                sequence_number=post_frame.sequence,
                timestamp_ms=post_frame.timestamp_ms,
            )
            await session.push_inbound_frame(post_audio_frame)
            self.inbound_frames_sent += 1

        # 8. Simulate Stop / Call Termination
        stop_event = NormalizedTelephonyEvent(
            event_type=TelephonyEventType.STOP,
            call_id=self.call_sid,
            session_id=self.session_id,
        )
        assert stop_event.event_type == TelephonyEventType.STOP

        # 9. Disconnect and Teardown
        await session.close(reason="simulator_normal_clearing")
        await session_manager.remove_session(self.session_id)

        return SimulatedCallResult(
            call_sid=self.call_sid,
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            organization_id=self.organization_id,
            agent_id=self.agent_id,
            inbound_frames_sent=self.inbound_frames_sent,
            outbound_frames_received=self.outbound_frames_received,
            dtmf_events_sent=len(self.dtmf_sent),
            interruptions_triggered=self.interruptions_triggered,
            final_connection_state=session.connection_state,
            success=True,
            details={"dtmf_digits": self.dtmf_sent},
        )


class TelephonySimulatorHarness:
    """High-level harness for executing single and concurrent simulated call scenarios."""

    def __init__(self, secret: str = "test_mock_webhook_secret_key_12345") -> None:
        self.webhook_client: SimulatedWebhookClient = SimulatedWebhookClient(
            secret=secret
        )
        self.audio_generator: SyntheticAudioGenerator = SyntheticAudioGenerator()

    async def run_simulated_call(
        self,
        call_sid: str = "call_sim_e2e_001",
        session_id: str = "session_sim_e2e_001",
        from_number: str = "+919876543210",
        to_number: str = "+911140001234",
        num_frames: int = 5,
        simulate_barge_in: bool = True,
    ) -> SimulatedCallResult:
        """Run a single simulated call against the global session manager."""
        session_manager = get_realtime_session_manager()
        call = SimulatedTelephonyCall(
            call_sid=call_sid,
            session_id=session_id,
            from_number=from_number,
            to_number=to_number,
        )
        return await call.execute_full_lifecycle(
            session_manager=session_manager,
            num_inbound_frames=num_frames,
            simulate_barge_in=simulate_barge_in,
        )

    async def run_concurrent_calls(
        self,
        count: int = 5,
        base_sid: str = "call_sim_conc",
        base_session: str = "session_sim_conc",
    ) -> list[SimulatedCallResult]:
        """Run N simultaneous simulated calls concurrently and verify complete isolation."""
        session_manager = get_realtime_session_manager()
        calls = [
            SimulatedTelephonyCall(
                call_sid=f"{base_sid}_{i:03d}",
                session_id=f"{base_session}_{i:03d}",
                from_number=f"+91987654{i:04d}",
                organization_id=f"org_sim_{i:02d}",
                tenant_id=f"tenant_sim_{i:02d}",
            )
            for i in range(1, count + 1)
        ]

        tasks = [
            call.execute_full_lifecycle(
                session_manager=session_manager,
                num_inbound_frames=4,
                simulate_barge_in=True,
            )
            for call in calls
        ]

        results = await asyncio.gather(*tasks)
        return list(results)

    def run_webhook_flow(
        self,
        client: TestClient,
        call_sid: str = "call_webhook_sim_001",
        from_number: str = "+919876543210",
        to_number: str = "+911140001234",
    ) -> Any:
        """Execute HTTP webhook intake verification flow."""
        payload = self.webhook_client.build_inbound_payload(
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
        )
        return self.webhook_client.send_inbound_webhook(client=client, payload=payload)
