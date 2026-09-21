"""Unit tests for Exotel Telecom Carrier Integration.

Verifies Exotel provider adaptation, safe credential handling,
REST API client behavior, and normalization of carrier events.
NOTE: All tests use synthetic mock fixtures. Real credentials are NEVER
baked into test assertions or fixtures.
"""

from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from backend.app.services.telephony.clients.exotel_client import (
    ExotelApiClient,
    ExotelAuthStatus,
)
from backend.app.services.telephony.config import TelephonySettings
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.events import TelephonyEventType
from backend.app.services.telephony.providers.exotel import ExotelTelephonyProvider


@pytest.fixture
def mock_exotel_settings() -> TelephonySettings:
    """Fixture providing synthetic Exotel settings without real secrets."""
    return TelephonySettings(
        exotel_account_sid="mock_acc_123",
        exotel_api_key=SecretStr("mock_key_abc"),
        exotel_api_token=SecretStr("mock_token_xyz"),
        exotel_base_url="https://api.in.exotel.com",
        exotel_exophone="022-000-00000",
    )


def test_exotel_settings_configuration_detection(mock_exotel_settings: TelephonySettings) -> None:
    """Test that all Exotel configuration fields are properly detected and reported safely."""
    assert mock_exotel_settings.is_exotel_configured is True
    report = mock_exotel_settings.get_exotel_status_report()
    assert report["exotel_configuration"] == "configured"
    assert report["exotel_account"] == "configured"
    assert report["exotel_api_credentials"] == "configured"
    assert report["exotel_exophone"] == "configured"
    assert report["exotel_base_url"] == "https://api.in.exotel.com"


def test_exotel_settings_partial_missing() -> None:
    """Test that incomplete settings are correctly flagged as missing."""
    empty_settings = TelephonySettings(
        exotel_account_sid="",
        exotel_api_key=SecretStr(""),
        exotel_api_token=SecretStr(""),
        exotel_exophone="",
    )
    assert empty_settings.is_exotel_configured is False
    report = empty_settings.get_exotel_status_report()
    assert report["exotel_configuration"] == "missing"
    assert report["exotel_account"] == "missing"
    assert report["exotel_api_credentials"] == "missing"
    assert report["exotel_exophone"] == "missing"


def test_exotel_secret_masking(mock_exotel_settings: TelephonySettings) -> None:
    """Verify that SecretStr prevents accidental credential leakage in str and repr."""
    key_str = str(mock_exotel_settings.exotel_api_key)
    token_repr = repr(mock_exotel_settings.exotel_api_token)
    assert "mock_key_abc" not in key_str
    assert "mock_token_xyz" not in token_repr
    assert "**********" in key_str


@pytest.mark.asyncio
async def test_exotel_api_client_verify_auth_success(mock_exotel_settings: TelephonySettings) -> None:
    """Test successful authentication against Exotel Accounts API using mock client."""
    mock_resp = httpx.Response(status_code=200, json={"Account": {"Sid": "mock_acc_123"}})
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.get.return_value = mock_resp

    client = ExotelApiClient(settings=mock_exotel_settings, http_client=mock_http)
    status = await client.verify_authentication()

    assert isinstance(status, ExotelAuthStatus)
    assert status.is_authenticated is True
    assert status.status_code == 200
    mock_http.get.assert_called_once()
    called_url = mock_http.get.call_args[0][0]
    assert "mock_acc_123" in called_url


@pytest.mark.asyncio
async def test_exotel_api_client_verify_auth_invalid(mock_exotel_settings: TelephonySettings) -> None:
    """Test 401 unauthorized handling during authentication check."""
    mock_resp = httpx.Response(status_code=401, json={"RestException": {"Message": "Authenticate"}})
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.get.return_value = mock_resp

    client = ExotelApiClient(settings=mock_exotel_settings, http_client=mock_http)
    status = await client.verify_authentication()

    assert status.is_authenticated is False
    assert status.status_code == 401


@pytest.mark.asyncio
async def test_exotel_api_client_verify_exophone(mock_exotel_settings: TelephonySettings) -> None:
    """Test verifying Exophone number association with account."""
    mock_resp = httpx.Response(status_code=200, json={"Number": {"PhoneNumber": "022-000-00000"}})
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.get.return_value = mock_resp

    client = ExotelApiClient(settings=mock_exotel_settings, http_client=mock_http)
    is_valid = await client.verify_exophone()
    assert is_valid is True


@pytest.mark.asyncio
async def test_exotel_api_client_transfer_call(mock_exotel_settings: TelephonySettings) -> None:
    """Test initiating call transfer via Exotel API."""
    mock_resp = httpx.Response(status_code=200, json={"Call": {"Sid": "call_123"}})
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.post.return_value = mock_resp

    client = ExotelApiClient(settings=mock_exotel_settings, http_client=mock_http)
    result = await client.transfer_call(call_id="call_123", target_phone_number="+919876543210")
    assert result["status"] == "transfer_initiated"
    assert result["call_id"] == "call_123"


def test_exotel_provider_inbound_normalization(mock_exotel_settings: TelephonySettings) -> None:
    """Test normalizing Exotel inbound webhook dictionary."""
    provider = ExotelTelephonyProvider(settings=mock_exotel_settings)
    raw = {
        "CallSid": "exotel_call_999",
        "From": "+919876500000",
        "To": "022-000-00000",
        "CallType": "trans",
        "Direction": "inbound",
        "DialWhomNumber": "+919876500000",
    }
    event = provider.normalize_inbound_call(raw)
    assert event.event_type == TelephonyEventType.CALL_CONNECTED
    assert event.call_id == "exotel_call_999"
    assert event.from_number == "+919876500000"
    assert event.to_number == "022-000-00000"
    assert event.provider_name == "exotel"
    assert event.provider_metadata["call_type"] == "trans"


def test_exotel_provider_inbound_missing_call_sid(mock_exotel_settings: TelephonySettings) -> None:
    """Test rejection when CallSid is missing."""
    provider = ExotelTelephonyProvider(settings=mock_exotel_settings)
    with pytest.raises(GatewayError) as exc_info:
        provider.normalize_inbound_call({"From": "+919999999999"})
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED


def test_exotel_provider_media_normalization(mock_exotel_settings: TelephonySettings) -> None:
    """Test normalizing raw bytes and JSON media/DTMF frames."""
    provider = ExotelTelephonyProvider(settings=mock_exotel_settings)

    # 1. Raw audio bytes
    raw_audio = b"\x00\x01\x02\x03" * 160
    audio_event = provider.normalize_media_event(raw_audio, call_id="call_999")
    assert audio_event.event_type == TelephonyEventType.MEDIA
    assert audio_event.payload == raw_audio

    # 2. JSON control DTMF
    dtmf_event = provider.normalize_media_event(
        {"event": "dtmf", "digit": "4"},
        call_id="call_999",
    )
    assert dtmf_event.event_type == TelephonyEventType.DTMF
    assert dtmf_event.dtmf_digit == "4"


def test_exotel_provider_call_event_normalization(mock_exotel_settings: TelephonySettings) -> None:
    """Test normalizing Exotel call lifecycle callbacks."""
    provider = ExotelTelephonyProvider(settings=mock_exotel_settings)

    # Completed call callback
    completed_event = provider.normalize_call_event(
        {
            "CallSid": "call_done_1",
            "Status": "completed",
            "Duration": "45",
            "RecordingUrl": "https://s3.amazonaws.com/exotel/rec1.mp3",
        }
    )
    assert completed_event.event_type == TelephonyEventType.STOP
    assert completed_event.call_id == "call_done_1"
    assert completed_event.provider_metadata["duration"] == "45"

    # Answered call callback
    active_event = provider.normalize_call_event(
        {
            "CallSid": "call_active_1",
            "Status": "in-progress",
        }
    )
    assert active_event.event_type == TelephonyEventType.CALL_CONNECTED


@pytest.mark.asyncio
async def test_exotel_provider_health_check(mock_exotel_settings: TelephonySettings) -> None:
    """Test provider health readiness check."""
    provider = ExotelTelephonyProvider(settings=mock_exotel_settings)
    assert await provider.check_health() is True
