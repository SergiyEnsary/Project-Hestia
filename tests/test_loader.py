import pytest

from hestia.config import HestiaConfig, StrictConfig, ZephyrusConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.base import HestiaModule, RegisteredTool
from hestia.modules.kairos.module import KairosModule
from hestia.modules.loader import load_modules, teardown_modules
from hestia.modules.zephyrus.module import ZephyrusModule


@pytest.mark.asyncio
async def test_load_enabled_zephyrus():
    config = HestiaConfig(
        modules={"zephyrus": {"enabled": True, "default_location": "Austin", "units": "metric"}}
    )
    registry = ToolRegistry()
    modules = await load_modules(config, registry)

    assert len(modules) == 1
    assert isinstance(modules[0], ZephyrusModule)
    assert modules[0].display_name == "Zephyrus"
    assert len(registry.get_definitions()) == 2
    await teardown_modules(modules)


@pytest.mark.asyncio
async def test_skips_disabled_modules():
    config = HestiaConfig(modules={"zephyrus": {"enabled": False}})
    registry = ToolRegistry()
    modules = await load_modules(config, registry)

    assert modules == []
    assert registry.get_definitions() == []


@pytest.mark.asyncio
async def test_module_setup_failure_is_isolated(monkeypatch):
    class BrokenZephyrus(HestiaModule):
        slug = "zephyrus"
        display_name = "Broken"
        domain = "Test"
        config_type = ZephyrusConfig

        async def setup(self, config: StrictConfig) -> None:
            raise RuntimeError("private setup detail")

        async def teardown(self) -> None:
            return

        def get_tools(self) -> list[RegisteredTool]:
            return []

    monkeypatch.setattr(
        "hestia.modules.loader.MODULE_REGISTRY",
        {"zephyrus": BrokenZephyrus, "kairos": KairosModule},
    )
    config = HestiaConfig(modules={"zephyrus": {"enabled": True}})
    modules = await load_modules(config, ToolRegistry())
    assert modules == []
