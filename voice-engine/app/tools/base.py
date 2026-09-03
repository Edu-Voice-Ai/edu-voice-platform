"""BaseTool protocol, registry, and execution result representation."""
from typing import Protocol, runtime_checkable, Dict, Any, List, Optional
from dataclasses import dataclass, field
import json


@dataclass
class ToolExecutionResult:
    """Standardized tool output."""
    tool_name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_content_string(self) -> str:
        """Serialize data to LLM-readable JSON string."""
        if not self.success:
            return f"Error executing {self.tool_name}: {self.error}"
        return json.dumps(self.data, ensure_ascii=False)


@runtime_checkable
class BaseTool(Protocol):
    """Protocol for executable AI tools."""

    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        ...

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        ...


class ToolRegistry:
    """Registry maintaining available tools for an agent."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_openai_tool_schemas(self) -> List[Dict[str, Any]]:
        """Export tool definitions for LLM tool calling."""
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema
                }
            })
        return schemas
