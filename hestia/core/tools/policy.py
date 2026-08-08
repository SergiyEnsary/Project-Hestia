from __future__ import annotations

from dataclasses import dataclass

from hestia.core.tools.models import RiskLevel, ToolDefinition


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    error_code: str | None = None


class ToolExecutionPolicy:
    """Central fail-closed authorization policy for tool execution."""

    def authorize(self, definition: ToolDefinition) -> PolicyDecision:
        if definition.risk_level is RiskLevel.WRITE:
            return PolicyDecision(
                allowed=False,
                error_code="write_confirmation_required",
            )
        return PolicyDecision(allowed=True)
