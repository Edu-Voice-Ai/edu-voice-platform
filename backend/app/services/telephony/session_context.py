"""Session Security Context and Tenant Isolation.

Enforces multi-tenant boundary checks ensuring sessions cannot access or leak
another organization's state.
"""

from typing import Any

from pydantic import BaseModel, Field

from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode


class SessionSecurityContext(BaseModel):
    """Immutable security and multi-tenant context associated with a call session."""

    session_id: str = Field(
        ...,
        min_length=1,
        description="Internal Gateway session identifier",
    )
    call_id: str = Field(
        ...,
        min_length=1,
        description="Telecom provider assigned call identifier",
    )
    organization_id: str | None = Field(
        default=None,
        description="Tenant organization identifier owning the phone assignment",
    )
    agent_id: str | None = Field(
        default=None,
        description="AI agent identity assigned to handle the call",
    )
    agent_config: Any | None = Field(
        default=None,
        description="Resolved agent speech, prompt, and handoff configuration",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive session metadata",
    )

    def assert_tenant_access(self, target_organization_id: str) -> None:
        """Verify that operations are strictly scoped to the session's organization."""
        if not self.organization_id:
            # Unbound session
            return

        if self.organization_id != target_organization_id:
            raise GatewayError(
                code=GatewayErrorCode.AUTHENTICATION_FAILED,
                message=(
                    f"Tenant isolation violation: Session org '{self.organization_id}' "
                    f"cannot access target org '{target_organization_id}'"
                ),
            )
