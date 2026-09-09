import pytest
from app.conversation.handoff_detector import (
    MultilingualHandoffDetector,
    HandoffDetectionResult,
)
from app.session.state import SessionState, HandoffStateEnum
from app.tools.handoff import (
    RequestHumanHandoffTool,
    HANDOFF_ROLE_ENUM,
    HANDOFF_DEPARTMENT_ENUM,
)


class TestMultilingualHandoffDetector:
    @pytest.fixture
    def detector(self):
        return MultilingualHandoffDetector()

    def test_ve_01_english_explicit_handoff(self, detector):
        """TEST-VE-01: English explicit handoff requests"""
        phrases = [
            ("I want to talk to an admission counselor", "admission_counselor", "admissions"),
            ("Can you connect me to a human?", "general_counselor", "general"),
            ("Please transfer my call to the accounts department", "accounts_officer", "accounts"),
            ("Let me speak to the principal", "principal", "academics"),
            ("Connect me to the hostel warden please", "hostel_warden", "hostel"),
            ("Transfer this call to an agent", "general_counselor", "general"),
        ]
        for phrase, expected_role, expected_dept in phrases:
            result = detector.detect(phrase)
            assert result.is_handoff_requested is True, f"Failed on: {phrase}"
            assert result.confidence >= 0.85, f"Low confidence {result.confidence} on: {phrase}"
            assert result.requested_role == expected_role
            assert result.requested_department == expected_dept
            assert result.is_ambiguous is False

            announcement = detector.get_holding_announcement(result.requested_role, "en-IN")
            assert "hold" in announcement.lower()

    def test_ve_02_telugu_explicit_handoff(self, detector):
        """TEST-VE-02: Telugu explicit handoff requests (Telugu script & transliteration)"""
        phrases = [
            ("నాకు అడ్మిషన్ కౌన్సిలర్‌తో మాట్లాడాలి", "admission_counselor", "admissions"),
            ("దయచేసి ఒక మనిషితో మాట్లాడించండి", "general_counselor", "general"),
            ("ప్రిన్సిపాల్ గారితో మాట్లాడాలి", "principal", "academics"),
            ("హోస్టల్ వార్డెన్ కి కాల్ ట్రాన్స్‌ఫర్ చేయండి", "hostel_warden", "hostel"),
            ("human tho matladali", "general_counselor", "general"),
            ("counselor tho matladandi", "admission_counselor", "admissions"),
        ]
        for phrase, expected_role, expected_dept in phrases:
            result = detector.detect(phrase, lang="te-IN")
            assert result.is_handoff_requested is True, f"Failed on: {phrase}"
            assert result.confidence >= 0.85, f"Low confidence {result.confidence} on: {phrase}"
            assert result.requested_role == expected_role
            assert result.requested_department == expected_dept
            assert result.is_ambiguous is False

            announcement = detector.get_holding_announcement(result.requested_role, "te-IN")
            assert "దయచేసి వేచి ఉండండి" in announcement

    def test_ve_03_hindi_explicit_handoff(self, detector):
        """TEST-VE-03: Hindi explicit handoff requests (Devanagari & Hinglish)"""
        phrases = [
            ("मुझे एडमिशन काउंसलर से बात करनी है", "admission_counselor", "admissions"),
            ("कृपया मुझे किसी इंसान से कनेक्ट करें", "general_counselor", "general"),
            ("अकाउंट्स डिपार्टमेंट से बात कराओ", "accounts_officer", "accounts"),
            ("प्रिंसिपल सर से बात करनी है", "principal", "academics"),
            ("hostel warden se connect karo", "hostel_warden", "hostel"),
            ("human agent se baat karni hai", "general_counselor", "general"),
        ]
        for phrase, expected_role, expected_dept in phrases:
            result = detector.detect(phrase, lang="hi-IN")
            assert result.is_handoff_requested is True, f"Failed on: {phrase}"
            assert result.confidence >= 0.85, f"Low confidence {result.confidence} on: {phrase}"
            assert result.requested_role == expected_role
            assert result.requested_department == expected_dept
            assert result.is_ambiguous is False

            announcement = detector.get_holding_announcement(result.requested_role, "hi-IN")
            assert "कृपया प्रतीक्षा करें" in announcement

    def test_ve_04_ambiguous_request_no_handoff(self, detector):
        """TEST-VE-04: Ambiguous / low-confidence request -> clarification, no handoff"""
        ambiguous_phrases = [
            "Are you a human?",
            "Are you an AI?",
            "Do you have counselors?",
            "Is there anyone there?",
        ]
        for phrase in ambiguous_phrases:
            result = detector.detect(phrase)
            assert result.is_handoff_requested is False, f"Erroneously triggered handoff on: {phrase}"
            assert result.is_ambiguous is True
            assert result.confidence < 0.85
            assert result.clarification_prompt is not None

    def test_general_query_no_handoff(self, detector):
        """Standard knowledge queries must NOT trigger handoff"""
        general_phrases = [
            "What is the fee structure for BTech?",
            "Tell me about hostel facilities",
            "Where is the campus located?",
            "What are the placement statistics?",
        ]
        for phrase in general_phrases:
            result = detector.detect(phrase)
            assert result.is_handoff_requested is False
            assert result.is_ambiguous is False
            assert result.confidence == 0.0

    def test_cancellation_detection(self, detector):
        """Caller can cancel a transfer before completion"""
        cancellations = [
            "never mind",
            "cancel the transfer",
            "don't transfer",
            "వద్దు లెండి",
            "ट्रांसफर मत कीजिए",
        ]
        for phrase in cancellations:
            result = detector.detect(phrase)
            assert result.is_cancellation is True, f"Failed to detect cancellation on: {phrase}"
            assert result.is_handoff_requested is False

    def test_fallback_announcements(self, detector):
        """Verify natural fallback announcements across languages"""
        en_fb = detector.get_fallback_announcement(reason="NO_ELIGIBLE_STAFF", lang="en-IN")
        assert "counselors are currently assisting other callers" in en_fb

        te_fb = detector.get_fallback_announcement(reason="busy", lang="te-IN")
        assert "క్షమించండి" in te_fb

        hi_fb = detector.get_fallback_announcement(reason="no_answer", lang="hi-IN")
        assert "क्षमा करें" in hi_fb


class TestHandoffStateMachineAndIdempotency:
    def test_handoff_lifecycle_and_idempotency(self):
        state = SessionState(session_id="test_session", organization_id="test_org", agent_id="test_agent")
        assert state.handoff_state == HandoffStateEnum.IDLE
        assert state.can_trigger_handoff() is True

        # 1. Trigger handoff
        state.record_handoff_requested(
            role="admission_counselor",
            department="admissions",
            reason="Explicit caller request",
            confidence=0.95
        )
        assert state.handoff_state == HandoffStateEnum.REQUESTED
        assert state.handoff_requested_role == "admission_counselor"
        assert state.handoff_requested_department == "admissions"
        assert state.handoff_confidence == 0.95

        # IDEMPOTENCY: Cannot trigger another handoff while in handoff lifecycle
        assert state.can_trigger_handoff() is False

        # 2. Acknowledge handoff
        state.record_handoff_acknowledged(hold_media=True)
        assert state.handoff_state == HandoffStateEnum.AWAITING_TRANSFER
        assert state.handoff_hold_media is True
        assert state.can_trigger_handoff() is False

        # 3. Fallback recovery
        state.record_handoff_fallback()
        assert state.handoff_state == HandoffStateEnum.FALLBACK_RECOVERY

        # After recovery, state can be reset to IDLE and can handoff again if needed
        state.reset_handoff_to_idle()
        assert state.handoff_state == HandoffStateEnum.IDLE
        assert state.can_trigger_handoff() is True

    def test_cancellation_state_transition(self):
        state = SessionState(session_id="test_session", organization_id="test_org", agent_id="test_agent")
        state.record_handoff_requested(
            role="accounts_officer",
            department="accounts",
            reason="Caller asked for accounts"
        )
        assert state.handoff_state == HandoffStateEnum.REQUESTED

        state.record_handoff_cancelled()
        assert state.handoff_state == HandoffStateEnum.CANCELLED

        state.reset_handoff_to_idle()
        assert state.handoff_state == HandoffStateEnum.IDLE
        assert state.can_trigger_handoff() is True

    def test_ai_triggered_escalation(self):
        detector = MultilingualHandoffDetector()

        # Turn 1 failure -> no handoff
        res1 = detector.detect("Can you explain the quantum mechanics curriculum?", out_of_scope_turns=1)
        assert res1.is_handoff_requested is False

        # Turn 2 consecutive failure -> AI-triggered escalation!
        res2 = detector.detect("Can you explain the quantum mechanics curriculum?", out_of_scope_turns=2)
        assert res2.is_handoff_requested is True
        assert res2.confidence >= 0.85
        assert "2 consecutive out-of-scope" in res2.reason

        # High frustration score -> AI-triggered escalation!
        res3 = detector.detect("This is useless, you are not answering anything", frustration_score=0.90)
        assert res3.is_handoff_requested is True
        assert res3.confidence >= 0.85
        assert "high caller frustration" in res3.reason


class TestRequestHumanHandoffTool:
    def test_tool_definition_and_canonical_roles(self):
        tool = RequestHumanHandoffTool()
        props = tool.parameters_schema["properties"]
        assert "requested_role" in props
        assert "requested_department" in props
        assert "reason" in props
        assert "confidence" in props
        assert tool.parameters_schema["required"] == ["requested_role", "reason"]

        for role in HANDOFF_ROLE_ENUM:
            assert role in props["requested_role"]["enum"]
        for dept in HANDOFF_DEPARTMENT_ENUM:
            assert dept in props["requested_department"]["enum"]

    @pytest.mark.asyncio
    async def test_tool_execution_output(self):
        tool = RequestHumanHandoffTool()
        res = await tool.execute(
            organization_id="test_org",
            agent_id="test_agent",
            requested_role="admission_counselor",
            requested_department="admissions",
            reason="Caller asked for admission details",
            confidence=0.92,
        )
        assert res.success is True
        assert res.data["event"] == "handoff.requested"
        assert res.data["requested_role"] == "admission_counselor"
        assert res.data["requested_department"] == "admissions"
        assert res.data["reason"] == "Caller asked for admission details"
        assert res.data["confidence"] == 0.92
        # Backwards compatible type field
        assert res.data["type"] == "human_handoff_requested"


class TestProviderAgnosticSecurityBoundary:
    def test_no_phone_numbers_in_handoff_structures(self):
        """Ensure handoff tools and detectors do not accept or emit telephony data"""
        tool = RequestHumanHandoffTool()
        props = tool.parameters_schema["properties"]
        assert "phone_number" not in props
        assert "destination" not in props
        assert "pstn" not in props
        assert "exotel" not in props

        detector = MultilingualHandoffDetector()
        res = detector.detect("Please connect me to an admission counselor at 9876543210")
        assert res.is_handoff_requested is True
        # Detector role and dept must not contain any phone number
        assert "9876543210" not in res.requested_role
        assert "9876543210" not in res.requested_department
