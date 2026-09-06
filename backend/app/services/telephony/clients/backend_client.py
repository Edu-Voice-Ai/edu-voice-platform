"""Backend Service HTTP Client for Telephony Call Status Notifications.

Implements Contract 4:
- Dispatches status callbacks to Aravind's Backend internal endpoint:
  POST /api/v1/internal/telephony/outbound-calls/{call_id}/status
- Authenticates using X-Internal-Service-Key
- Handles network errors and timeouts gracefully
"""

import logging

import httpx

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.outbound_schemas import (
    OutboundCallStatusCallbackPayload,
)

logger = logging.getLogger("telephony.backend.client")


class BackendStatusCallbackClient:
    """Async HTTP client dispatching call status events to the Backend service."""

    def __init__(
        self,
        settings: TelephonySettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings: TelephonySettings = settings or get_telephony_settings()
        self._external_client = http_client

    @property
    def base_url(self) -> str:
        return self.settings.backend_internal_url.rstrip("/")

    @property
    def internal_service_key(self) -> str:
        return self.settings.internal_service_key.get_secret_value()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(timeout=5.0)

    async def send_call_status(
        self,
        payload: OutboundCallStatusCallbackPayload,
    ) -> bool:
        """Post call status event to Backend service.

        Returns True on successful delivery (HTTP 200/202/204), False on failure.
        """
        endpoint = f"{self.base_url}/api/v1/internal/telephony/outbound-calls/{payload.call_id}/status"
        headers = {
            "Content-Type": "application/json",
            "X-Internal-Service-Key": self.internal_service_key,
        }

        # Convert Pydantic payload to JSON dict
        body_dict = payload.model_dump(mode="json")

        client = await self._get_client()
        should_close = self._external_client is None

        try:
            resp = await client.post(endpoint, json=body_dict, headers=headers)
            if resp.status_code in (200, 201, 202, 204):
                logger.info(
                    "Delivered call status '%s' to Backend for call_id=%s (status_code=%s)",
                    payload.status.value,
                    payload.call_id,
                    resp.status_code,
                )
                return True

            logger.warning(
                "Backend rejected status '%s' for call_id=%s: status_code=%s, body=%s",
                payload.status.value,
                payload.call_id,
                resp.status_code,
                resp.text[:200],
            )
            return False
        except (httpx.RequestError, OSError) as req_err:
            logger.warning(
                "Failed to deliver call status '%s' for call_id=%s to Backend: %s",
                payload.status.value,
                payload.call_id,
                str(req_err),
            )
            return False
        finally:
            if should_close:
                await client.aclose()
