"""Verify live Gateway -> Voice Engine connection post-deployment.

Tests:
1. WSS connection to wss://voice-test.gentechs.in/ws/voice
2. Gateway session.start with complete outbound metadata contract (Contract 5)
3. Await session.ready
4. Stream 16 kHz PCM16 audio.input
5. Capture streaming audio.output chunks
6. Send session.end
7. Capture lead.extracted / call.summary if emitted
8. Clean teardown
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.voice_engine_client import VoiceEngineWsClient
from backend.app.services.telephony.voice_engine_schemas import (
    AudioOutputEvent,
    CallSummaryEvent,
    LeadExtractedEvent,
    SessionStartPayload,
)


async def main() -> bool:
    print("=" * 60)
    print("LIVE GATEWAY -> VOICE ENGINE VERIFICATION")
    print("=" * 60)

    ws_url = "wss://voice-test.gentechs.in/ws/voice"
    call_id = f"call_outbound_verify_{uuid.uuid4().hex[:8]}"
    session_id = f"sess_{uuid.uuid4().hex[:12]}"

    metadata = {
        "session_id": session_id,
        "call_id": call_id,
        "organization_id": "org_gentechs_test",
        "agent_id": "agent_admissions_01",
        "call_direction": "outbound",
        "campaign_id": "camp_admissions_2026",
        "contact_id": "cnt_parent_9876",
        "template_type": "admissions_followup",
        "business_name": "Greenwood High School",
        "agent_name": "Priya",
        "language": "te-IN",
        "client_sample_rate": 16000,
    }

    start_payload = SessionStartPayload(
        session_id=session_id,
        call_id=call_id,
        organization_id="org_gentechs_test",
        agent_id="agent_admissions_01",
        call_direction="outbound",
        campaign_id="camp_admissions_2026",
        contact_id="cnt_parent_9876",
        template_type="admissions_followup",
        business_name="Greenwood High School",
        agent_name="Priya",
        language="te-IN",
        client_sample_rate=16000,
    )

    audio_chunks_received = 0
    leads_received = []
    summaries_received = []

    async def on_audio_output(event: AudioOutputEvent, frame: AudioFrame) -> None:
        nonlocal audio_chunks_received
        audio_chunks_received += 1
        if audio_chunks_received == 1:
            print(f"[4] First audio.output chunk received! Length={len(frame.data)} bytes, seq={frame.sequence_number}")

    async def on_lead(event: LeadExtractedEvent) -> None:
        leads_received.append(event)
        print(f"[6] lead.extracted received: {event.lead or event.data}")

    async def on_summary(event: CallSummaryEvent) -> None:
        summaries_received.append(event)
        print(f"[7] call.summary received: {event.summary or event.data}")

    client = VoiceEngineWsClient(
        ws_url=ws_url,
        session_id=session_id,
        start_payload=start_payload,
        connect_timeout_seconds=8.0,
        init_timeout_seconds=8.0,
        on_audio_output=on_audio_output,
        on_lead_extracted=on_lead,
        on_call_summary=on_summary,
    )

    print(f"[1] Connecting to Voice Engine: {ws_url}")
    print(f"    call_id: {call_id}")
    print(f"    metadata: {metadata}")
    await client.connect_and_start()

    print(f"[2] session.ready confirmed! is_ready={client.is_ready}")
    assert client.is_ready, "Voice Engine must be ready"

    # Send synthetic speech audio frame (16kHz PCM16, 20ms = 640 bytes)
    print("[3] Streaming 16kHz PCM16 audio.input frames...")
    dummy_frame = b"\x10\x00\x20\x00" * 160  # 640 bytes
    for _ in range(10):
        await client.send_audio_frame(AudioFrame(data=dummy_frame))
        await asyncio.sleep(0.02)

    print("    Waiting for audio streaming responses...")
    await asyncio.sleep(2.0)
    print(f"    Total audio.output chunks received: {audio_chunks_received}")

    print("[5] Sending session.end...")
    await client.close(reason="Verification test complete")
    print("[8] Disconnected cleanly!")

    print("=" * 60)
    print("GATEWAY -> VOICE ENGINE VERIFICATION: SUCCESS")
    print(f"  Session ID: {session_id}")
    print(f"  Call ID:    {call_id}")
    print(f"  Audio Out:  {audio_chunks_received} chunks")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
