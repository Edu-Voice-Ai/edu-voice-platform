"""Call routing and tenant DID resolution abstraction.

NOTE ON UNRESOLVED CONTRACT:
The DID-to-tenant lookup schema and backend database contract belong to
Aravind (Backend + Database). This module provides the required clean interface
boundary without fabricating database schemas or internal backend APIs.
"""

import abc
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("telephony.routing")


@dataclass(frozen=True)
class TenantRoutingResolution:
    """Resolution result associating an inbound DID with an organization and agent."""

    is_resolved: bool
    inbound_did: str
    organization_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    error_message: str | None = None


class BaseTenantCallRouter(abc.ABC):
    """Abstract interface for DID-to-Tenant routing."""

    @abc.abstractmethod
    async def resolve_did(self, inbound_did: str) -> TenantRoutingResolution:
        """Resolve an incoming phone number (DID) to its tenant organization and AI agent."""


class PhoneAssignmentTenantCallRouter(BaseTenantCallRouter):
    """Router integrating PhoneAssignmentResolver (including BackendPhoneAssignmentResolver) into the webhook flow."""

    def __init__(self, resolver: Any) -> None:
        self.resolver = resolver

    async def resolve_did(self, inbound_did: str) -> TenantRoutingResolution:
        from backend.app.services.telephony.errors import GatewayError
        from backend.app.services.telephony.routing.phone_assignment import (
            PhoneAssignmentRequest,
        )

        try:
            result = await self.resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number=inbound_did)
            )
            return TenantRoutingResolution(
                is_resolved=True,
                inbound_did=inbound_did,
                organization_id=result.organization_id,
                agent_id=result.agent_id,
                agent_type=result.agent_type,
            )
        except GatewayError as ge:
            return TenantRoutingResolution(
                is_resolved=False,
                inbound_did=inbound_did,
                error_message=ge.message,
            )


class UnresolvedBackendTenantCallRouter(BaseTenantCallRouter):
    """Fallback router returning provisional routing when backend is unconfigured."""

    async def resolve_did(self, inbound_did: str) -> TenantRoutingResolution:
        logger.info(
            "DID resolution invoked for DID '%s' (Backend DID router in default mode)",
            inbound_did,
        )
        return TenantRoutingResolution(
            is_resolved=True,
            inbound_did=inbound_did,
            organization_id="pending_contract_org",
            agent_id="pending_contract_admission_agent",
            agent_type="admission_ai",
        )
