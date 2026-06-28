import pytest

from hestia.config import HestiaConfig
from hestia.core.tools.registry import ToolRegistry
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
