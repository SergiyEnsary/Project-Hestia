from __future__ import annotations

import json
import logging
from typing import Any

from hestia.core.tools.models import ToolDefinition, ToolHandler, ToolResult
from hestia.modules.base import HestiaModule

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register_module(self, module: HestiaModule) -> None:
        for tool in module.get_tools():
            name = tool.definition.name
            if name in self._tools:
                raise ValueError(f"Duplicate tool name: {name}")
            self._tools[name] = tool.definition
            self._handlers[name] = tool.handler

    def get_definitions(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_tool_summary(self) -> str:
        lines = []
        for name, defn in self._tools.items():
            lines.append(f"- {name}: {defn.description}")
        return "\n".join(lines)

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self._handlers:
            return ToolResult(name=name, content=f"Unknown tool: {name}", is_error=True)

        defn = self._tools[name]
        try:
            self._validate_arguments(defn, arguments)
            content = await self._handlers[name](arguments)
            return ToolResult(name=name, content=content)
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return ToolResult(name=name, content=str(exc), is_error=True)

    def _validate_arguments(self, defn: ToolDefinition, arguments: dict[str, Any]) -> None:
        required = defn.parameters.get("required", [])
        props = defn.parameters.get("properties", {})
        for key in required:
            if key not in arguments:
                raise ValueError(f"Missing required argument: {key}")
        for key in arguments:
            if key not in props:
                raise ValueError(f"Unknown argument: {key}")

    def format_result(self, result: ToolResult) -> str:
        if result.is_error:
            return f"Error from {result.name}: {result.content}"
        try:
            parsed = json.loads(result.content)
            return json.dumps(parsed, indent=2)
        except (json.JSONDecodeError, TypeError):
            return result.content
