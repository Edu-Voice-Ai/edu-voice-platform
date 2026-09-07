"""Human Handoff tool and event payload."""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolExecutionResult
from app.core.logging import get_logger

logger = get_logger("tools.handoff")


class HandoffEventPayload(BaseModel):
    """Structured payload emitted when human handoff is requested."""
    type: str = "human_handoff_requested"
    organization_id: str
    agent_id: str
    session_id: str
    reason: str
    priority: str = "normal"  # normal, high, urgent
    caller_intent: Optional[str] = None


class RequestHumanHandoffTool(BaseTool):
    """Tool triggered when caller requests a human counselor or when facts cannot be verified."""

    @property
    def name(self) -> str:
        return "request_human_handoff"

    @property
    def description(self) -> str:
        return "Escalate the conversation to a human admission officer when the caller asks for human assistance or questions cannot be verified."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Reason for transfer"},
                "priority": {"type": "string", "enum": ["normal", "high", "urgent"], "default": "normal"}
            },
            "required": ["reason"]
        }

    async def execute(self, organization_id: str, agent_id: str, reason: str = "Caller requested human assistance", priority: str = "normal", **kwargs) -> ToolExecutionResult:
        logger.info(f"Human handoff initiated for org={organization_id}: {reason} (priority: {priority})")
        return ToolExecutionResult(
            tool_name=self.name,
            success=True,
            data={
                "type": "human_handoff_requested",
                "organization_id": organization_id,
                "reason": reason,
                "priority": priority,
                "status": "HANDOFF_SCHEDULED"
            }
        )
