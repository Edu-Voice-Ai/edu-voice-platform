"""Phone Number Assignment and Tenant Routing Resolution Boundary.

Provides provider-neutral abstractions and production-ready HTTP resolver
connecting the Voice Gateway to Aravind's internal FastAPI DID resolution service.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, Field

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode

logger = logging.getLogger("telephony.routing.phone_assignment")


class ResolvedAgentConfig(BaseModel):
    """Complete speech, prompt, handoff, and runtime parameters for a resolved AI agent."""

    organization_id: str = Field(..., description="Tenant organization identifier")
    organization_name: str | None = Field(
        default=None, description="Human-readable organization name"
    )
    organization_slug: str | None = Field(
        default=None, description="Organization slug identifier"
    )
    agent_id: str = Field(..., description="Assigned agent identifier")
    agent_name: str | None = Field(
        default=None, description="Human-readable agent name"
    )
    agent_type: str = Field(default="admission_ai", description="Role/type of AI agent")
    is_active: bool = Field(default=True, description="Whether agent is active")
    system_prompt: str | None = Field(
        default=None, description="Base system instructions for LLM"
    )
    voice_id: str | None = Field(default=None, description="Synthesizer voice profile")
    voice_speed: float = Field(default=1.0, description="Playback speed multiplier")
    language: str = Field(default="en-IN", description="Primary interaction language")
    supported_languages: list[str] = Field(
        default_factory=lambda: ["en-IN"],
        description="List of supported multilingual language codes",
    )
    allow_barge_in: bool = Field(
        default=True, description="Whether caller speech interrupts bot playback"
    )
    vad_silence_threshold_ms: int = Field(
        default=400, description="Silence duration to detect turn end"
    )
    welcome_message: str | None = Field(
        default=None, description="Initial greeting prompt played on call answer"
    )
    human_handoff_enabled: bool = Field(
        default=True, description="Master toggle for human counselor escalation"
    )
    human_handoff_number: str | None = Field(
        default=None, description="Escalation phone number (E.164)"
    )
    human_handoff_condition: str = Field(
        default="on_request_or_unknown",
        description="Condition triggering human handoff",
    )
    max_call_duration_seconds: int = Field(
        default=600, description="Maximum call lifetime limit in seconds"
    )
    custom_settings: dict[str, Any] = Field(
        default_factory=dict, description="Extensible agent parameters"
    )


class PhoneAssignmentRequest(BaseModel):
    """Request to resolve a dialed destination phone number."""

    phone_number: str = Field(
        ...,
        min_length=3,
        description="Destination phone number in standard dialing format (e.g. +91XXXXXXXXXX)",
    )
    caller_number: str | None = Field(
        default=None,
        description="Caller / originating phone number if available",
    )
    provider: str | None = Field(
        default=None,
        description="Telephony provider name (e.g. 'exotel', 'telephony')",
    )
    call_sid: str | None = Field(
        default=None,
        description="Telecom provider call identifier if available",
    )


class PhoneAssignmentResult(BaseModel):
    """Resolved tenant and agent assignment for an inbound phone number."""

    phone_number: str = Field(..., description="Target phone number")
    organization_id: str = Field(..., description="Tenant organization identifier")
    agent_id: str = Field(..., description="Assigned agent identifier")
    agent_type: str = Field(
        default="admission_counselor", description="Role/type of AI agent"
    )
    is_active: bool = Field(
        default=True, description="Whether the DID assignment is currently active"
    )
    transfer_number: str | None = Field(
        default=None, description="Escalation human fallback phone number"
    )
    agent_config: ResolvedAgentConfig | None = Field(
        default=None,
        description="Full agent configuration resolved from backend",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Custom routing configuration"
    )


class PhoneAssignmentResolver(ABC):
    """Abstract interface for resolving phone numbers to tenant organizations and agents."""

    @abstractmethod
    async def resolve_phone_assignment(
        self,
        request: PhoneAssignmentRequest,
    ) -> PhoneAssignmentResult:
        """Resolve phone number to tenant organization and assigned AI agent."""


class InMemoryPhoneAssignmentResolver(PhoneAssignmentResolver):
    """In-memory resolver for local testing and deterministic mock routing."""

    def __init__(
        self, initial_mappings: dict[str, PhoneAssignmentResult] | None = None
    ) -> None:
        self._mappings: dict[str, PhoneAssignmentResult] = initial_mappings or {}

    def register_assignment(self, result: PhoneAssignmentResult) -> None:
        """Register a test mapping."""
        self._mappings[result.phone_number] = result

    async def resolve_phone_assignment(
        self,
        request: PhoneAssignmentRequest,
    ) -> PhoneAssignmentResult:
        """Resolve from in-memory test mapping."""
        normalized = request.phone_number.strip()
        if normalized in self._mappings:
            return self._mappings[normalized]

        raise GatewayError(
            code=GatewayErrorCode.VALIDATION_FAILED,
            message=f"No active phone assignment found for destination number '{request.phone_number}'",
        )


class BackendPhoneAssignmentResolver(PhoneAssignmentResolver):
    """Production HTTP client resolver connecting to Aravind's FastAPI backend service.

    Features:
    - Asynchronous HTTP via httpx
    - X-Internal-Service-Key authentication
    - Configurable timeout (default 2.0s)
    - Zero direct database / Supabase credential access
    - Support for both canonical ARAVIND_YASIN_SUPABASE_CONTRACT.md and VOICE_GATEWAY_INTEGRATION.md payload shapes
    - Timing-safe, sanitized error mapping without SQL / secret leakage
    """

    _shared_client: httpx.AsyncClient | None = None

    @classmethod
    def get_shared_client(cls, timeout_seconds: float) -> httpx.AsyncClient:
        """Get or initialize the shared persistent HTTP client with connection pooling."""
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=50,
                    keepalive_expiry=60.0,
                ),
            )
        return cls._shared_client

    @classmethod
    async def close_shared_client(cls) -> None:
        """Gracefully close the shared HTTP client."""
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None

    def __init__(
        self,
        backend_url: str | None = None,
        internal_service_key: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
        settings: TelephonySettings | None = None,
    ) -> None:
        self.settings = settings or get_telephony_settings()
        self.backend_url = (backend_url or self.settings.backend_internal_url).rstrip(
            "/"
        )
        self.internal_service_key = (
            internal_service_key
            if internal_service_key is not None
            else self.settings.internal_service_key.get_secret_value()
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else (self.settings.did_resolve_timeout_ms / 1000.0)
        )
        self._external_client = client

    def _get_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._external_client is not None:
            return self._external_client, False
        return self.get_shared_client(self.timeout_seconds), False

    async def resolve_phone_assignment(
        self,
        request: PhoneAssignmentRequest,
    ) -> PhoneAssignmentResult:
        """Query Aravind's backend endpoint to resolve DID to tenant and agent config."""
        endpoint = f"{self.backend_url}/api/v1/internal/telephony/resolve-did"
        headers = {
            "Content-Type": "application/json",
            "X-Internal-Service-Key": self.internal_service_key,
        }
        # Canonical backend resolve-did contract payload
        payload = {
            "phone_number": request.phone_number,
        }

        client, should_close = self._get_client()
        http_req_start_ns = time.perf_counter_ns()

        try:
            response = await client.post(endpoint, json=payload, headers=headers)
            http_res_received_ns = time.perf_counter_ns()
            result = self._parse_response(response, request.phone_number)
            response_parsed_ns = time.perf_counter_ns()

            if result.metadata is None:
                result.metadata = {}
            result.metadata["timing"] = {
                "http_req_start_ns": http_req_start_ns,
                "http_res_received_ns": http_res_received_ns,
                "response_parsed_ns": response_parsed_ns,
                "http_roundtrip_ms": round((http_res_received_ns - http_req_start_ns) / 1_000_000, 2),
                "parse_duration_ms": round((response_parsed_ns - http_res_received_ns) / 1_000_000, 2),
            }
            return result
        except httpx.TimeoutException as exc:
            logger.error(
                "Backend DID resolution timed out for phone %s", request.phone_number
            )
            raise GatewayError(
                code=GatewayErrorCode.TIMEOUT,
                message=f"Backend DID resolution timed out after {self.timeout_seconds:.1f}s",
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Backend DID resolution connection error: %s", str(exc))
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="FastAPI backend service is unavailable for DID resolution",
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    def _parse_response(
        self, response: httpx.Response, requested_phone: str
    ) -> PhoneAssignmentResult:
        """Parse HTTP response and map structured backend data or errors."""
        status_code = response.status_code

        # Attempt to parse JSON body
        try:
            body = response.json()
        except (ValueError, TypeError):
            body = {}

        if status_code == 200:
            data = body.get("data", {}) if isinstance(body, dict) else {}
            if not data:
                raise GatewayError(
                    code=GatewayErrorCode.INTERNAL_ERROR,
                    message="Malformed backend response: missing 'data' field",
                )
            return self._build_result_from_data(data, requested_phone)

        # Handle structured error codes
        err_obj = (
            body.get("error", {})
            if isinstance(body, dict) and isinstance(body.get("error"), dict)
            else {}
        )
        error_code_str = (
            err_obj.get("code") or body.get("detail") or "UNKNOWN_BACKEND_ERROR"
        )
        error_msg = err_obj.get("message") or body.get("message") or str(error_code_str)

        logger.warning(
            "Backend DID resolution rejected: status=%s, code=%s, msg=%s",
            status_code,
            error_code_str,
            error_msg,
        )

        if status_code == 401 or error_code_str in (
            "UNAUTHORIZED_INTERNAL_SERVICE",
            "INVALID_INTERNAL_KEY",
        ):
            raise GatewayError(
                code=GatewayErrorCode.AUTHENTICATION_FAILED,
                message="Unauthorized internal service authentication with backend",
            )
        if status_code == 404 or error_code_str in (
            "DID_NOT_FOUND",
            "AGENT_NOT_ASSIGNED",
        ):
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message=f"DID '{requested_phone}' not found or not assigned: {error_msg}",
            )
        if status_code in (403, 409) or error_code_str in (
            "DID_INACTIVE",
            "PHONE_INACTIVE",
            "ORGANIZATION_INACTIVE",
            "AGENT_INACTIVE",
        ):
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message=f"DID or assigned entity inactive: {error_msg}",
            )
        if status_code == 422 or error_code_str in (
            "NO_ACTIVE_ASSIGNMENT",
            "INVALID_DID_FORMAT",
        ):
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message=f"Invalid DID assignment state: {error_msg}",
            )
        if status_code == 503 or error_code_str == "DATABASE_UNAVAILABLE":
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="Backend database is currently unavailable",
            )

        # Generic fallback
        raise GatewayError(
            code=GatewayErrorCode.INTERNAL_ERROR,
            message=f"Backend DID resolution failed with status {status_code}: {error_msg}",
        )

    def _build_result_from_data(
        self, data: dict[str, Any], fallback_phone: str
    ) -> PhoneAssignmentResult:
        """Extract both nested contract schema and flat integration guide schema."""
        phone_number = data.get("phone_number") or fallback_phone
        organization_id = data.get("organization_id", "")
        agent_id = data.get("agent_id", "")
        agent_name = data.get("agent_name")
        agent_type = data.get("agent_type", "admission_ai")
        is_active = data.get("is_active", True)

        # Extract nested configs if present (Contract 1)
        speech_cfg = (
            data.get("speech_config", {})
            if isinstance(data.get("speech_config"), dict)
            else {}
        )
        handoff_cfg = (
            data.get("handoff_config", {})
            if isinstance(data.get("handoff_config"), dict)
            else {}
        )

        # Fallbacks for flat format (Guide 2)
        primary_lang = (
            speech_cfg.get("primary_language") or data.get("language") or "en-IN"
        )
        supported_langs = (
            speech_cfg.get("supported_languages")
            or data.get("supported_languages")
            or [primary_lang]
        )
        voice_id = speech_cfg.get("voice_id") or data.get("voice_id")
        voice_speed = float(
            speech_cfg.get("voice_speed") or data.get("voice_speed") or 1.0
        )
        allow_barge_in = bool(
            speech_cfg.get("allow_barge_in", data.get("allow_barge_in", True))
        )
        vad_silence = int(
            speech_cfg.get(
                "vad_silence_threshold_ms", data.get("vad_silence_threshold_ms", 400)
            )
        )
        welcome_msg = speech_cfg.get("welcome_message") or data.get("welcome_message")
        max_duration = int(
            speech_cfg.get(
                "max_call_duration_seconds", data.get("max_call_duration_seconds", 600)
            )
        )
        system_prompt = speech_cfg.get("system_prompt") or data.get("system_prompt")

        human_handoff_enabled = bool(
            handoff_cfg.get(
                "human_handoff_enabled", data.get("human_handoff_enabled", True)
            )
        )
        human_handoff_number = handoff_cfg.get("human_handoff_number") or data.get(
            "human_handoff_number"
        )
        human_handoff_condition = (
            handoff_cfg.get("human_handoff_condition")
            or data.get("human_handoff_condition")
            or "on_request_or_unknown"
        )

        agent_config = ResolvedAgentConfig(
            organization_id=organization_id,
            organization_name=data.get("organization_name"),
            organization_slug=data.get("organization_slug"),
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=agent_type,
            is_active=is_active,
            system_prompt=system_prompt,
            voice_id=voice_id,
            voice_speed=voice_speed,
            language=primary_lang,
            supported_languages=supported_langs,
            allow_barge_in=allow_barge_in,
            vad_silence_threshold_ms=vad_silence,
            welcome_message=welcome_msg,
            human_handoff_enabled=human_handoff_enabled,
            human_handoff_number=human_handoff_number,
            human_handoff_condition=human_handoff_condition,
            max_call_duration_seconds=max_duration,
            custom_settings=data.get("custom_settings") or {},
        )

        return PhoneAssignmentResult(
            phone_number=phone_number,
            organization_id=organization_id,
            agent_id=agent_id,
            agent_type=agent_type,
            is_active=is_active,
            transfer_number=human_handoff_number,
            agent_config=agent_config,
            metadata={
                "organization_name": data.get("organization_name"),
                "agent_name": agent_name,
                "welcome_message": welcome_msg,
            },
        )
