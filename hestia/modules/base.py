from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from hestia.config import StrictConfig
from hestia.core.tools.models import ToolDefinition, ToolHandler


class HestiaModule(ABC):
    slug: str
    display_name: str
    domain: str
    config_type: type[StrictConfig]

    @abstractmethod
    async def setup(self, config: StrictConfig) -> None:
        """Initialize the module from validated configuration."""

    @abstractmethod
    async def teardown(self) -> None:
        """Release resources owned by the module."""

    @abstractmethod
    def get_tools(self) -> list[RegisteredTool]:
        """Return all tools exposed by the module."""


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler
