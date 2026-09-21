"""Simulated Webhook Client for Local Telephony Sandbox (TEST ONLY).

Constructs, signs, and dispatches simulated inbound phone call webhooks
and call status event callbacks.

NOTE: Uses test-only HMAC secrets and mock payloads. Does NOT connect to external telecom carriers.
"""

import hashlib
import hmac
import json
import time
from typing import Any

from fastapi.testclient import TestClient


class SimulatedWebhookClient:
    """Helper client to simulate telecom webhook callbacks with HMAC signing."""

    def __init__(
        self,
        secret: str = "test_mock_webhook_secret_key_12345",
        base_url: str = "/api/v1/telephony",
    ) -> None:
        self.secret: str = secret
        self.base_url: str = base_url

    def compute_signature(
        self, payload_bytes: bytes, timestamp: int | None = None
    ) -> str:
        """Compute HMAC-SHA256 signature over timestamp and payload bytes."""
        if timestamp is not None:
            message = f"{timestamp}.".encode() + payload_bytes
        else:
            message = payload_bytes
        return hmac.new(
            self.secret.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()

    def build_inbound_payload(
        self,
        call_sid: str = "call_sim_001",
        from_number: str = "+919876543210",
        to_number: str = "+911140001234",
        direction: str = "inbound",
        status: str = "initiated",
        custom_parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Construct standard inbound call webhook dictionary."""
        return {
            "call_sid": call_sid,
            "from_number": from_number,
            "to_number": to_number,
            "direction": direction,
            "call_status": status,
            "custom_parameters": custom_parameters or {"campaign": "admission_2026"},
        }

    def build_event_payload(
        self,
        call_sid: str = "call_sim_001",
        event_type: str = "call_disconnected",
        call_status: str = "completed",
        duration_seconds: int = 45,
        hangup_cause: str = "normal_clearing",
        recording_url: str | None = None,
    ) -> dict[str, Any]:
        """Construct call lifecycle status callback dictionary."""
        return {
            "call_sid": call_sid,
            "event_type": event_type,
            "call_status": call_status,
            "duration_seconds": duration_seconds,
            "hangup_cause": hangup_cause,
            "recording_url": recording_url,
        }

    def send_inbound_webhook(
        self,
        client: TestClient,
        payload: dict[str, Any] | None = None,
        custom_secret: str | None = None,
        tamper_signature: bool = False,
        timestamp_offset_seconds: int = 0,
        omit_signature: bool = False,
        raw_body: str | None = None,
    ) -> Any:
        """Send simulated inbound webhook request with HMAC signature headers."""
        if raw_body is not None:
            body_bytes = raw_body.encode("utf-8")
        else:
            payload_data = payload or self.build_inbound_payload()
            body_bytes = json.dumps(payload_data).encode("utf-8")

        timestamp = int(time.time()) + timestamp_offset_seconds
        secret_to_use = custom_secret or self.secret

        if tamper_signature:
            signature = "tampered_invalid_hmac_signature_hex_value_00000000"
        else:
            if timestamp is not None:
                message = f"{timestamp}.".encode() + body_bytes
            else:
                message = body_bytes
            signature = hmac.new(
                secret_to_use.encode(), message, hashlib.sha256
            ).hexdigest()

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if not omit_signature:
            headers["X-Telephony-Signature"] = signature
            headers["X-Telephony-Timestamp"] = str(timestamp)

        return client.post(
            f"{self.base_url}/webhook",
            content=body_bytes,
            headers=headers,
        )

    def send_event_callback(
        self,
        client: TestClient,
        payload: dict[str, Any] | None = None,
        tamper_signature: bool = False,
    ) -> Any:
        """Send simulated call status event callback with HMAC headers."""
        payload_data = payload or self.build_event_payload()
        body_bytes = json.dumps(payload_data).encode("utf-8")
        timestamp = int(time.time())

        if tamper_signature:
            signature = "invalid_signature_hex_value"
        else:
            message = f"{timestamp}.".encode() + body_bytes
            signature = hmac.new(
                self.secret.encode(), message, hashlib.sha256
            ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Telephony-Signature": signature,
            "X-Telephony-Timestamp": str(timestamp),
        }

        return client.post(
            f"{self.base_url}/events",
            content=body_bytes,
            headers=headers,
        )
