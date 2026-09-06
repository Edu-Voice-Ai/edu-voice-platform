"""Telephony / Voice Gateway Service Package."""

from backend.app.services.telephony.clients.backend_client import (
    BackendStatusCallbackClient,
)
from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import (
    GatewayError,
    GatewayErrorCode,
)
from backend.app.services.telephony.events import (
    NormalizedTelephonyEvent,
    TelephonyEventType,
)
from backend.app.services.telephony.frames import (
    AudioFrame,
    FrameType,
    InternalAudioMessage,
)
from backend.app.services.telephony.gateway import WebSocketAudioGateway
from backend.app.services.telephony.idempotency import (
    IdempotencyConflictError,
    PersistentIdempotencyStore,
    get_idempotency_store,
)
from backend.app.services.telephony.lifecycle.session import (
    CallSession,
    CallSessionLifecycleManager,
    CallSessionState,
)
from backend.app.services.telephony.limiter import (
    GatewayRateLimiter,
    get_gateway_rate_limiter,
)
from backend.app.services.telephony.logging import (
    StructuredGatewayLogger,
    sanitize_dict,
    sanitize_value,
)
from backend.app.services.telephony.metrics import (
    GatewayMetrics,
    get_gateway_metrics,
)
from backend.app.services.telephony.mock_stream import MockAudioStreamClient
from backend.app.services.telephony.outbound_schemas import (
    OutboundCallRequest,
    OutboundCallResponse,
    OutboundCallStatus,
    OutboundCallStatusCallbackPayload,
)
from backend.app.services.telephony.providers.base import BaseTelephonyProvider
from backend.app.services.telephony.providers.generic import GenericTelephonyProvider
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    RealtimeVoiceSession,
    SessionStats,
)
from backend.app.services.telephony.routing.phone_assignment import (
    BackendPhoneAssignmentResolver,
    InMemoryPhoneAssignmentResolver,
    PhoneAssignmentRequest,
    PhoneAssignmentResolver,
    PhoneAssignmentResult,
)
from backend.app.services.telephony.routing.resolver import (
    BaseTenantCallRouter,
    TenantRoutingResolution,
    UnresolvedBackendTenantCallRouter,
)
from backend.app.services.telephony.schemas import (
    CallDirection,
    CallEventType,
    CallStatus,
    CallStatusEventPayload,
    HealthResponse,
    InboundCallPayload,
    TelephonyWebhookResponse,
)
from backend.app.services.telephony.security.verifier import (
    BaseWebhookVerifier,
    HMACSHA256WebhookVerifier,
    WebhookVerificationResult,
)
from backend.app.services.telephony.service import TelephonyService
from backend.app.services.telephony.session_context import SessionSecurityContext
from backend.app.services.telephony.session_manager import (
    RealtimeSessionManager,
    get_realtime_session_manager,
)
from backend.app.services.telephony.voice_engine_client import VoiceEngineWsClient
from backend.app.services.telephony.voice_engine_contract import (
    BaseVoiceEngineTransport,
    UnresolvedVoiceEngineAdapter,
    WsVoiceEngineTransport,
    build_session_start_payload,
)
from backend.app.services.telephony.voice_engine_schemas import (
    AudioOutputData,
    AudioOutputEvent,
    CallSummaryEvent,
    LeadExtractedEvent,
    ResponseCancelledData,
    ResponseCancelledEvent,
    ResponseEndData,
    ResponseEndEvent,
    SessionEndPayload,
    SessionReadyEvent,
    SessionStartPayload,
    VoiceEngineErrorEvent,
    VoiceEngineEventType,
    VoiceEngineTemplateType,
)

__all__ = [
    "AudioFrame",
    "AudioOutputData",
    "AudioOutputEvent",
    "BackendPhoneAssignmentResolver",
    "BackendStatusCallbackClient",
    "BaseTelephonyProvider",
    "BaseTenantCallRouter",
    "BaseVoiceEngineTransport",
    "BaseWebhookVerifier",
    "CallDirection",
    "CallEventType",
    "CallSession",
    "CallSessionLifecycleManager",
    "CallSessionState",
    "CallStatus",
    "CallStatusEventPayload",
    "CallSummaryEvent",
    "ConnectionState",
    "FrameType",
    "GatewayError",
    "GatewayErrorCode",
    "GatewayMetrics",
    "GatewayRateLimiter",
    "GenericTelephonyProvider",
    "HMACSHA256WebhookVerifier",
    "HealthResponse",
    "IdempotencyConflictError",
    "InMemoryPhoneAssignmentResolver",
    "InboundCallPayload",
    "InternalAudioMessage",
    "LeadExtractedEvent",
    "MockAudioStreamClient",
    "NormalizedTelephonyEvent",
    "OutboundCallRequest",
    "OutboundCallResponse",
    "OutboundCallStatus",
    "OutboundCallStatusCallbackPayload",
    "PersistentIdempotencyStore",
    "PhoneAssignmentRequest",
    "PhoneAssignmentResolver",
    "PhoneAssignmentResult",
    "RealtimeSessionManager",
    "RealtimeVoiceSession",
    "ResponseCancelledData",
    "ResponseCancelledEvent",
    "ResponseEndData",
    "ResponseEndEvent",
    "SessionEndPayload",
    "SessionReadyEvent",
    "SessionSecurityContext",
    "SessionStartPayload",
    "SessionStats",
    "StructuredGatewayLogger",
    "TelephonyEventType",
    "TelephonyService",
    "TelephonySettings",
    "TelephonyWebhookResponse",
    "TenantRoutingResolution",
    "UnresolvedBackendTenantCallRouter",
    "UnresolvedVoiceEngineAdapter",
    "VoiceEngineErrorEvent",
    "VoiceEngineEventType",
    "VoiceEngineTemplateType",
    "VoiceEngineWsClient",
    "WebSocketAudioGateway",
    "WebhookVerificationResult",
    "WsVoiceEngineTransport",
    "build_session_start_payload",
    "get_gateway_metrics",
    "get_gateway_rate_limiter",
    "get_idempotency_store",
    "get_realtime_session_manager",
    "get_telephony_settings",
    "sanitize_dict",
    "sanitize_value",
]
