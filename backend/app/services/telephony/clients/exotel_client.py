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
from backend.app.services.telephony.logging import (
    StructuredGatewayLogger,
    mask_identifier,
)

logger = logging.getLogger("telephony.exotel.client")
slog = StructuredGatewayLogger("telephony.exotel.client")


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
        headers = {"Accept": "application/json"}

        client = await self._get_client()
        should_close = self._http_client is None
        masked_target = mask_identifier(target_phone_number)
        masked_call_id = mask_identifier(call_id)
        slog.info(
            "exotel_transfer_call_requested",
            call_id=masked_call_id,
            target_phone=masked_target,
            account_sid=self.account_sid,
        )

        try:
            payload = {
                "PhoneNumber": target_phone_number,
                "CallerId": self.exophone,
            }
            resp = await client.post(url, data=payload, headers=headers, auth=auth)
            resp_body_snippet = resp.text[:500]
            slog.info(
                "exotel_transfer_call_response",
                call_id=masked_call_id,
                status_code=resp.status_code,
                response_body=resp_body_snippet,
            )

            if resp.status_code in (200, 201, 202):
                return {
                    "status": "transfer_initiated",
                    "call_id": call_id,
                    "target_phone_number": target_phone_number,
                    "provider": "exotel",
                }

            # Parse error details safely
            err_detail = resp_body_snippet
            try:
                err_json = resp.json()
                if "RestException" in err_json:
                    err_detail = str(err_json["RestException"].get("Message", resp_body_snippet))
            except (ValueError, KeyError, TypeError):
                logger.debug("Non-JSON or malformed error response from Exotel: %s", resp_body_snippet)

            slog.error(
                "exotel_transfer_call_failed",
                call_id=masked_call_id,
                status_code=resp.status_code,
                error_detail=err_detail,
            )

            raise GatewayError(
                code=GatewayErrorCode.CONNECTION_FAILED,
                message=f"Exotel call transfer failed with status {resp.status_code}: {err_detail}",
            )
        except httpx.TimeoutException as exc:
            slog.error("exotel_transfer_call_timeout", call_id=masked_call_id)
            raise GatewayError(
                code=GatewayErrorCode.TIMEOUT,
                message=f"Exotel call transfer request timed out: {exc}",
            ) from exc
        except httpx.HTTPError as exc:
            slog.error("exotel_transfer_call_http_error", call_id=masked_call_id, error=str(exc))
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message=f"Exotel call transfer communication error: {exc}",
            ) from exc
        finally:
            if should_close:
                await client.aclose()

