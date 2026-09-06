"""Exotel Telecom Carrier REST API Client.

Handles secure communication with Exotel's cloud telephony platform.
All sensitive credentials (API Key, API Token) are handled as SecretStr
and never exposed in logs or exception representations.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode

logger = logging.getLogger("telephony.exotel.client")


@dataclass(frozen=True)
class ExotelAuthStatus:
    """Safe authentication verification status without secret leakage."""

    is_authenticated: bool
    account_sid: str
    status_code: int
    message: str


class ExotelApiClient:
    """Async HTTP client for Exotel carrier operations."""

    def __init__(
        self,
        settings: TelephonySettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings: TelephonySettings = settings or get_telephony_settings()
        self._http_client = http_client

    @property
    def account_sid(self) -> str:
        return self.settings.exotel_account_sid.strip()

    @property
    def exophone(self) -> str:
        return self.settings.exotel_exophone.strip()

    @property
    def base_url(self) -> str:
        return self.settings.exotel_base_url.rstrip("/")

    def _get_auth_tuple(self) -> tuple[str, str]:
        """Return HTTP Basic Auth credentials tuple safely."""
        return (
            self.settings.exotel_api_key.get_secret_value().strip(),
            self.settings.exotel_api_token.get_secret_value().strip(),
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is not None:
            return self._http_client
        return httpx.AsyncClient(timeout=10.0)

    async def verify_authentication(self) -> ExotelAuthStatus:
        """Verify Exotel account credentials against Accounts endpoint."""
        if not self.settings.is_exotel_configured:
            return ExotelAuthStatus(
                is_authenticated=False,
                account_sid=self.account_sid or "unknown",
                status_code=400,
                message="Exotel configuration is incomplete or missing",
            )

        url = f"{self.base_url}/v1/Accounts/{self.account_sid}"
        auth = self._get_auth_tuple()

        client = await self._get_client()
        should_close = self._http_client is None
        try:
            resp = await client.get(url, auth=auth)
            if resp.status_code == 200:
                logger.info("Exotel authentication verified successfully for account")
                return ExotelAuthStatus(
                    is_authenticated=True,
                    account_sid=self.account_sid,
                    status_code=200,
                    message="Exotel account credentials verified successfully",
                )
            if resp.status_code == 401:
                logger.warning("Exotel authentication failed: invalid credentials")
                return ExotelAuthStatus(
                    is_authenticated=False,
                    account_sid=self.account_sid,
                    status_code=401,
                    message="Exotel authentication failed: invalid API key or token",
                )
            return ExotelAuthStatus(
                is_authenticated=False,
                account_sid=self.account_sid,
                status_code=resp.status_code,
                message=f"Exotel returned unexpected status code: {resp.status_code}",
            )
        except (httpx.HTTPError, OSError) as err:
            logger.error("Error communicating with Exotel API: %s", type(err).__name__)
            return ExotelAuthStatus(
                is_authenticated=False,
                account_sid=self.account_sid,
                status_code=500,
                message=f"Exotel connection error: {type(err).__name__}",
            )
        finally:
            if should_close:
                await client.aclose()

    async def verify_exophone(self) -> bool:
        """Verify that the configured Exophone is associated with the account."""
        if not self.settings.is_exotel_configured or not self.exophone:
            return False

        url = f"{self.base_url}/v1/Accounts/{self.account_sid}/Numbers/{self.exophone}"
        auth = self._get_auth_tuple()

        client = await self._get_client()
        should_close = self._http_client is None
        try:
            resp = await client.get(url, auth=auth)
            return resp.status_code == 200
        except (httpx.HTTPError, OSError):
            return False
        finally:
            if should_close:
                await client.aclose()

    async def transfer_call(
        self,
        call_id: str,
        target_phone_number: str,
    ) -> dict[str, Any]:
        """Initiate human transfer via Exotel API."""
        if not self.settings.is_exotel_configured:
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="Cannot initiate transfer: Exotel credentials not configured",
            )

        url = f"{self.base_url}/v1/Accounts/{self.account_sid}/Calls/{call_id}"
        auth = self._get_auth_tuple()

        client = await self._get_client()
        should_close = self._http_client is None
        try:
            payload = {
                "PhoneNumber": target_phone_number,
                "CallerId": self.exophone,
            }
            resp = await client.post(url, data=payload, auth=auth)
            if resp.status_code in (200, 201, 202):
                return {
                    "status": "transfer_initiated",
                    "call_id": call_id,
                    "target_phone_number": target_phone_number,
                    "provider": "exotel",
                }
            raise GatewayError(
                code=GatewayErrorCode.CONNECTION_FAILED,
                message=f"Exotel call transfer failed with status {resp.status_code}",
            )
        finally:
            if should_close:
                await client.aclose()

    async def initiate_outbound_call(
        self,
        from_phone_number: str,
        to_phone_number: str,
        applet_url: str | None = None,
        custom_field: str | None = None,
        status_callback_url: str | None = None,
    ) -> dict[str, Any]:
        """Initiate outbound customer call connecting to Exotel applet or flow.

        Parameters:
        - from_phone_number: Authorized caller ID (ExoPhone)
        - to_phone_number: Customer phone number to dial
        - applet_url: Dynamic URL or flow applet webhook
        - custom_field: Contextual string (e.g. gateway_call_id or call_id)
        - status_callback_url: Webhook for status callbacks
        """
        if not self.settings.is_exotel_configured:
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="Exotel credentials not configured for outbound dialing",
            )

        url = f"{self.base_url}/v1/Accounts/{self.account_sid}/Calls/connect.json"
        auth = self._get_auth_tuple()

        payload: dict[str, str] = {
            "From": to_phone_number,
            "CallerId": from_phone_number,
        }
        if applet_url:
            payload["Url"] = applet_url
        if custom_field:
            payload["CustomField"] = custom_field
        if status_callback_url:
            payload["StatusCallback"] = status_callback_url

        client = await self._get_client()
        should_close = self._http_client is None

        try:
            resp = await client.post(url, data=payload, auth=auth)
            if resp.status_code in (200, 201, 202):
                data = resp.json()
                call_data = data.get("Call", {}) if isinstance(data, dict) else {}
                provider_call_id = call_data.get("Sid") or data.get("Sid") or f"exotel_{to_phone_number}"
                provider_status = call_data.get("Status") or "queued"
                logger.info(
                    "Exotel outbound call initiated: provider_call_id=%s, status=%s",
                    provider_call_id,
                    provider_status,
                )
                return {
                    "provider": "exotel",
                    "provider_call_id": provider_call_id,
                    "status": provider_status,
                    "raw_response": data,
                }

            logger.error(
                "Exotel outbound call request failed: status_code=%s, response=%s",
                resp.status_code,
                resp.text[:200],
            )
            raise GatewayError(
                code=GatewayErrorCode.PROVIDER_UNAVAILABLE,
                message=f"Exotel rejected outbound call with status {resp.status_code}: {resp.text[:100]}",
            )
        except httpx.RequestError as exc:
            logger.error("Network error connecting to Exotel outbound API: %s", str(exc))
            raise GatewayError(
                code=GatewayErrorCode.PROVIDER_UNAVAILABLE,
                message=f"Network error connecting to Exotel outbound API: {exc}",
            ) from exc
        finally:
            if should_close:
                await client.aclose()
