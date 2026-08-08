from __future__ import annotations

import json
import logging
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from hestia.core.tools.confirmation import WriteConfirmationStore
from hestia.core.tools.models import RiskLevel, ToolDefinition, ToolHandler, ToolResult
from hestia.core.tools.policy import ToolExecutionPolicy
from hestia.modules.base import HestiaModule
from hestia.security.errors import get_correlation_id

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(
        self,
        policy: ToolExecutionPolicy | None = None,
        confirmations: WriteConfirmationStore | None = None,
    ) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._policy = policy or ToolExecutionPolicy()
        self._confirmations = confirmations or WriteConfirmationStore()

    @property
    def confirmations(self) -> WriteConfirmationStore:
        return self._confirmations

    def register_module(self, module: HestiaModule) -> None:
        for tool in module.get_tools():
            name = tool.definition.name
            if not name.startswith(f"{module.slug}."):
                raise ValueError(f"Tool {name!r} must use module namespace {module.slug!r}")
            if name in self._tools:
                raise ValueError(f"Duplicate tool name: {name}")
            self._validate_definition(tool.definition)
            self._tools[name] = tool.definition
            self._handlers[name] = tool.handler

    def get_definitions(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_tool_summary(self) -> str:
        lines = []
        for name, defn in self._tools.items():
            risk = f" [{defn.risk_level}]" if defn.risk_level is RiskLevel.WRITE else ""
            lines.append(f"- {name}{risk}: {defn.description}")
        return "\n".join(lines)

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        confirmed: bool = False,
    ) -> ToolResult:
        if name not in self._handlers:
            return self._error(name, "unknown_tool")

        defn = self._tools[name]
        decision = self._policy.authorize(defn, confirmed=confirmed)
        if not decision.allowed:
            if decision.error_code == "write_confirmation_required":
                try:
                    self._validate_arguments(defn, arguments)
                except ValidationError:
                    return self._error(name, "invalid_arguments")
                pending = self._confirmations.create(name, arguments)
                payload = {
                    "status": "confirmation_required",
                    "confirmation_id": pending.id,
                    "tool": name,
                    "arguments": pending.arguments,
                    "expires_at": pending.expires_at.isoformat(),
                    "message": (
                        "This write action requires explicit user confirmation via "
                        "POST /tools/confirm. Do not treat chat assent as confirmation."
                    ),
                }
                return ToolResult(
                    name=name,
                    content=json.dumps(payload),
                    is_error=True,
                    error_code="write_confirmation_required",
                )
            return self._error(
                name,
                decision.error_code or "tool_not_authorized",
            )
        try:
            self._validate_arguments(defn, arguments)
            content = await self._handlers[name](arguments)
            return ToolResult(name=name, content=content)
        except ValidationError:
            return self._error(name, "invalid_arguments")
        except Exception:
            correlation_id = get_correlation_id()
            logger.exception("Tool %s failed (correlation_id=%s)", name, correlation_id)
            return self._error(
                name,
                "tool_execution_failed",
                correlation_id=correlation_id,
            )

    async def confirm_and_execute(self, confirmation_id: str) -> ToolResult:
        pending = self._confirmations.consume(confirmation_id)
        if pending is None:
            return self._error("unknown", "invalid_or_expired_confirmation")
        return await self.execute(
            pending.tool_name,
            pending.arguments,
            confirmed=True,
        )

    def _validate_arguments(self, defn: ToolDefinition, arguments: dict[str, Any]) -> None:
        Draft202012Validator(
            defn.parameters,
            format_checker=FormatChecker(),
        ).validate(arguments)

    def _validate_definition(self, defn: ToolDefinition) -> None:
        try:
            Draft202012Validator.check_schema(defn.parameters)
        except SchemaError as exc:
            raise ValueError(f"Invalid schema for tool {defn.name}") from exc
        if defn.parameters.get("type") != "object":
            raise ValueError(f"Tool {defn.name} parameters must be an object schema")
        if defn.parameters.get("additionalProperties") is not False:
            raise ValueError(f"Tool {defn.name} must set additionalProperties to false")
        self._validate_schema_bounds(defn.name, defn.parameters, path="$")

    def _validate_schema_bounds(
        self,
        tool_name: str,
        schema: dict[str, Any],
        *,
        path: str,
    ) -> None:
        schema_type = schema.get("type")
        if schema_type == "string" and "maxLength" not in schema:
            raise ValueError(f"Tool {tool_name} has an unbounded string at {path}")
        if schema_type in {"integer", "number"} and (
            "minimum" not in schema or "maximum" not in schema
        ):
            raise ValueError(f"Tool {tool_name} has an unbounded number at {path}")
        if schema_type == "array":
            if "maxItems" not in schema:
                raise ValueError(f"Tool {tool_name} has an unbounded array at {path}")
            items = schema.get("items")
            if isinstance(items, dict):
                self._validate_schema_bounds(
                    tool_name,
                    items,
                    path=f"{path}[]",
                )
        if schema_type == "object":
            if schema.get("additionalProperties") is not False:
                raise ValueError(f"Tool {tool_name} has an open object at {path}")
            properties = schema.get("properties", {})
            if isinstance(properties, dict):
                for property_name, property_schema in properties.items():
                    if isinstance(property_schema, dict):
                        self._validate_schema_bounds(
                            tool_name,
                            property_schema,
                            path=f"{path}.{property_name}",
                        )

    @staticmethod
    def _error(
        name: str,
        error_code: str,
        *,
        correlation_id: str | None = None,
    ) -> ToolResult:
        return ToolResult(
            name=name,
            content="The tool could not be completed.",
            is_error=True,
            error_code=error_code,
            correlation_id=correlation_id,
        )

    def format_result(self, result: ToolResult) -> str:
        if result.is_error:
            if result.error_code == "write_confirmation_required":
                return (
                    f"Confirmation required for {result.name}. "
                    f"Present this payload to the user and wait for POST /tools/confirm: "
                    f"{result.content}"
                )
            suffix = f" Reference: {result.correlation_id}." if result.correlation_id else ""
            return f"Error from {result.name} ({result.error_code}): {result.content}{suffix}"
        try:
            parsed = json.loads(result.content)
            return json.dumps(parsed, indent=2)
        except (json.JSONDecodeError, TypeError):
            return result.content
