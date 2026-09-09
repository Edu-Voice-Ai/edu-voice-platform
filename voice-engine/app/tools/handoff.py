"""Human Handoff tool and event payload adhering to Universal Call Handoff Specifications."""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolExecutionResult
from app.core.logging import get_logger

logger = get_logger("tools.handoff")

HANDOFF_ROLE_ENUM: List[str] = [
    "admission_counselor",
    "accounts_officer",
    "principal",
    "hostel_warden",
    "administrator",
    "general_counselor",
]

HANDOFF_DEPARTMENT_ENUM: List[str] = [
    "admissions",
    "accounts",
    "administration",
    "hostel",
    "academics",
    "general",
]

ROLE_TO_DEPARTMENT: Dict[str, str] = {
    "admission_counselor": "admissions",
    "accounts_officer": "accounts",
    "principal": "academics",
    "hostel_warden": "hostel",
    "administrator": "administration",
    "general_counselor": "general",
}


class HandoffEventPayload(BaseModel):
    """Structured payload emitted when human handoff is requested."""
    event: str = "handoff.requested"
    type: str = "human_handoff_requested"  # Backwards compatibility
    session_id: str
    call_id: Optional[str] = None
    organization_id: str
    agent_id: str
    requested_role: str = "admission_counselor"
    requested_department: str = "admissions"
    reason: str
    confidence: float = 0.95
    timestamp: Optional[str] = None


class RequestHumanHandoffTool(BaseTool):
    """Tool triggered when caller requests a human counselor or when facts cannot be verified."""

    @property
    def name(self) -> str:
        return "request_human_handoff"

    @property
    def description(self) -> str:
        return "Trigger a transfer to an institutional staff member when the caller explicitly requests human assistance or when escalation is required."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "requested_role": {
                    "type": "string",
                    "enum": HANDOFF_ROLE_ENUM,
                    "description": "The institutional role requested by the caller."
                },
                "requested_department": {
                    "type": "string",
                    "enum": HANDOFF_DEPARTMENT_ENUM,
                    "description": "The department relevant to the caller's request."
                },
                "reason": {
                    "type": "string",
                    "description": "Brief description of why handoff is being initiated."
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score between 0.0 and 1.0."
                }
            },
            "required": ["requested_role", "reason"]
        }

    async def execute(
        self,
        organization_id: str,
        agent_id: str,
        requested_role: str = "admission_counselor",
        requested_department: Optional[str] = None,
        reason: str = "Caller requested human assistance",
        confidence: float = 0.95,
        priority: str = "normal",
        **kwargs
    ) -> ToolExecutionResult:
        # Default department from role if omitted
        dept = requested_department or ROLE_TO_DEPARTMENT.get(requested_role, "general")
        logger.info(
            f"Human handoff initiated for org={organization_id}, role={requested_role}, dept={dept}: {reason} (confidence: {confidence:.2f})"
        )
        return ToolExecutionResult(
            tool_name=self.name,
            success=True,
            data={
                "event": "handoff.requested",
                "type": "human_handoff_requested",  # Preserve legacy compatibility
                "organization_id": organization_id,
                "agent_id": agent_id,
                "requested_role": requested_role,
                "requested_department": dept,
                "reason": reason,
                "confidence": float(confidence),
                "priority": priority,
                "status": "HANDOFF_SCHEDULED"
            }
        )
