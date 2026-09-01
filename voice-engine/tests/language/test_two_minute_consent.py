"""Unit tests verifying the two-minute consent question immediately following language selection."""
import pytest
from app.session.state import SessionState
from app.conversation.manager import ConversationManager
from app.conversation.language import (
    CONSENT_REQUEST_PROMPT,
    CONSENT_YES_RESPONSE,
    CONSENT_NO_RESPONSE,
    CONSENT_AMBIGUOUS_CLARIFICATION,
    ConsentResponseParser
)


def test_consent_response_parser_variations():
    """Verify YES, NO, and AMBIGUOUS markers in English, Hindi, and Telugu."""
    # YES variations
    assert ConsentResponseParser.parse_consent_response("Yes") == "YES"
    assert ConsentResponseParser.parse_consent_response("Sure, please go ahead") == "YES"
    assert ConsentResponseParser.parse_consent_response("Okay") == "YES"
    assert ConsentResponseParser.parse_consent_response("हाँ") == "YES"
    assert ConsentResponseParser.parse_consent_response("जी हाँ") == "YES"
    assert ConsentResponseParser.parse_consent_response("हाँ बोलिए") == "YES"
    assert ConsentResponseParser.parse_consent_response("అవును") == "YES"
    assert ConsentResponseParser.parse_consent_response("సరే మాట్లాడండి") == "YES"
    assert ConsentResponseParser.parse_consent_response("అవునండి") == "YES"

    # NO variations
    assert ConsentResponseParser.parse_consent_response("No") == "NO"
    assert ConsentResponseParser.parse_consent_response("Not now, thanks") == "NO"
    assert ConsentResponseParser.parse_consent_response("नहीं") == "NO"
    assert ConsentResponseParser.parse_consent_response("अभी नहीं") == "NO"
    assert ConsentResponseParser.parse_consent_response("వద్దు") == "NO"
    assert ConsentResponseParser.parse_consent_response("ఇప్పుడు వద్దు") == "NO"
    assert ConsentResponseParser.parse_consent_response("లేదు") == "NO"

    # AMBIGUOUS variations
    assert ConsentResponseParser.parse_consent_response("Maybe") == "AMBIGUOUS"
    assert ConsentResponseParser.parse_consent_response("Not sure") == "AMBIGUOUS"
    assert ConsentResponseParser.parse_consent_response("ఏమో") == "AMBIGUOUS"
    assert ConsentResponseParser.parse_consent_response("చూద్దాం") == "AMBIGUOUS"
    assert ConsentResponseParser.parse_consent_response("देखते हैं") == "AMBIGUOUS"


def test_telugu_language_selection_and_consent_yes_flow():
    """Verify full Telugu language selection, consent question, and yes flow."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_te_consent", organization_id="org_test", agent_id="agent_1")

    # Turn 1: User selects Telugu
    ack_1 = manager.handle_language_selection_or_switch(session, "Telugu")
    assert ack_1 == CONSENT_REQUEST_PROMPT["te-IN"]
    assert ack_1 == "సరే, ఇక నుంచి మనం తెలుగులో మాట్లాడుకుందాం. మీతో రెండు నిమిషాలు మాట్లాడవచ్చా?"
    assert session.preferred_language == "te-IN"
    assert session.language_selection_complete is True
    assert session.waiting_for_consent is True
    assert session.two_minute_permission_asked is True
    assert session.conversation_state == "WAITING_FOR_TWO_MINUTE_CONSENT"

    # Turn 2: User says "అవును" (YES)
    ack_2 = manager.handle_language_selection_or_switch(session, "అవును")
    assert ack_2 == CONSENT_YES_RESPONSE["te-IN"]
    assert ack_2 == "ధన్యవాదాలు. మీకు ఏ course గురించి తెలుసుకోవాలి?"
    assert session.waiting_for_consent is False
    assert session.consent_granted is True
    assert session.conversation_state == "LISTENING"
    assert session.preferred_language == "te-IN"

    # Turn 3: User asks normal question - should not ask consent again
    ack_3 = manager.handle_language_selection_or_switch(session, "మీ దగ్గర ఏమేమి courses ఉన్నాయి?")
    assert ack_3 is None  # Goes to FastQueryRouter / LLM directly
    assert session.waiting_for_consent is False
    assert session.preferred_language == "te-IN"


def test_hindi_language_selection_and_consent_yes_flow():
    """Verify Hindi language selection, consent question, and yes flow."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_hi_consent", organization_id="org_test", agent_id="agent_1")

    # Turn 1: User selects Hindi
    ack_1 = manager.handle_language_selection_or_switch(session, "Hindi")
    assert ack_1 == CONSENT_REQUEST_PROMPT["hi-IN"]
    assert ack_1 == "ठीक है, अब हम हिंदी में बात करेंगे। क्या मैं आपसे दो मिनट बात कर सकता हूँ?"
    assert session.preferred_language == "hi-IN"
    assert session.waiting_for_consent is True

    # Turn 2: User says "हाँ" (YES)
    ack_2 = manager.handle_language_selection_or_switch(session, "हाँ")
    assert ack_2 == CONSENT_YES_RESPONSE["hi-IN"]
    assert ack_2 == "धन्यवाद। आप किस कोर्स के बारे में जानना चाहते हैं?"
    assert session.waiting_for_consent is False
    assert session.consent_granted is True
    assert session.conversation_state == "LISTENING"


def test_english_language_selection_and_consent_yes_flow():
    """Verify English language selection, consent question, and yes flow."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_en_consent", organization_id="org_test", agent_id="agent_1")

    # Turn 1: User selects English
    ack_1 = manager.handle_language_selection_or_switch(session, "English")
    assert ack_1 == CONSENT_REQUEST_PROMPT["en-IN"]
    assert ack_1 == "Sure, we can continue in English. May I speak with you for two minutes?"
    assert session.preferred_language == "en-IN"
    assert session.waiting_for_consent is True

    # Turn 2: User says "Yes, you can" (YES)
    ack_2 = manager.handle_language_selection_or_switch(session, "Yes, you can")
    assert ack_2 == CONSENT_YES_RESPONSE["en-IN"]
    assert ack_2 == "Thank you. Which course would you like to know about?"
    assert session.waiting_for_consent is False
    assert session.consent_granted is True


def test_telugu_consent_no_flow():
    """Verify polite closing when Telugu user says NO."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_te_no", organization_id="org_test", agent_id="agent_1")

    manager.handle_language_selection_or_switch(session, "Telugu")
    ack_no = manager.handle_language_selection_or_switch(session, "వద్దు")
    assert ack_no == CONSENT_NO_RESPONSE["te-IN"]
    assert ack_no == "పరవాలేదు. మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. మీ రోజు శుభంగా ఉండాలి."
    assert session.waiting_for_consent is False
    assert session.consent_granted is False
    assert session.conversation_state == "CLOSING"


def test_hindi_consent_no_flow():
    """Verify polite closing when Hindi user says NO."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_hi_no", organization_id="org_test", agent_id="agent_1")

    manager.handle_language_selection_or_switch(session, "Hindi")
    ack_no = manager.handle_language_selection_or_switch(session, "नहीं")
    assert ack_no == CONSENT_NO_RESPONSE["hi-IN"]
    assert ack_no == "कोई बात नहीं। आपका समय देने के लिए धन्यवाद। आपका दिन शुभ हो।"
    assert session.conversation_state == "CLOSING"


def test_english_consent_no_flow():
    """Verify polite closing when English user says NO."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_en_no", organization_id="org_test", agent_id="agent_1")

    manager.handle_language_selection_or_switch(session, "English")
    ack_no = manager.handle_language_selection_or_switch(session, "No, thank you")
    assert ack_no == CONSENT_NO_RESPONSE["en-IN"]
    assert ack_no == "No problem. Thank you for your time. Have a great day."
    assert session.conversation_state == "CLOSING"


def test_ambiguous_consent_flow_clarification_and_continuation():
    """Verify ambiguous response triggers clarification once, then opens to conversation."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_ambig", organization_id="org_test", agent_id="agent_1")

    # Select English
    manager.handle_language_selection_or_switch(session, "English")
    
    # Ambiguous reply 1: "Maybe"
    clarification = manager.handle_language_selection_or_switch(session, "Maybe")
    assert clarification == CONSENT_AMBIGUOUS_CLARIFICATION["en-IN"]
    assert clarification == "Would you like to continue?"
    assert session.waiting_for_consent is True
    assert session.consent_clarification_asked is True

    # User confirms: "Sure"
    ack_yes = manager.handle_language_selection_or_switch(session, "Sure")
    assert ack_yes == CONSENT_YES_RESPONSE["en-IN"]
    assert session.waiting_for_consent is False
    assert session.consent_granted is True
