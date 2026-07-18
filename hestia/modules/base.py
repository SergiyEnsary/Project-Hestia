from __future__ import annotations

from hestia.core.tools.models import ToolDefinition, ToolHandler
from typing import Protocol


class HestiaModule(Protocol):
    slug: str
    display_name: str
    domain: str

    async def setup(self, config: dict) -> None: ...
    async def teardown(self) -> None: ...
    def get_tools(self) -> list["RegisteredTool"]: ...


class RegisteredTool:
    def __init__(
        self,
        definition: ToolDefinition,
        handler: ToolHandler,
    ) -> None:
        self.definition = definition
        self.handler = handler
