import pytest

from hestia.config import (
    ClioConfig,
    HephaestusConfig,
    HermesConfig,
    HestiaConfig,
    IrisConfig,
    KairosConfig,
    StrictConfig,
    ZephyrusConfig,
)
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.base import HestiaModule, RegisteredTool
from hestia.modules.clio.module import ClioModule
from hestia.modules.hephaestus.module import HephaestusModule
from hestia.modules.hermes.module import HermesModule
from hestia.modules.iris.module import IrisModule
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
        {
            "zephyrus": BrokenZephyrus,
            "kairos": KairosModule,
            "clio": ClioModule,
            "hephaestus": HephaestusModule,
            "hermes": HermesModule,
            "iris": IrisModule,
        },
    )
    config = HestiaConfig(modules={"zephyrus": {"enabled": True}})
    modules = await load_modules(config, ToolRegistry())
    assert modules == []


def test_phase4_configs_default_disabled():
    config = HestiaConfig()
    assert isinstance(config.modules.clio, ClioConfig)
    assert config.modules.clio.enabled is False
    assert isinstance(config.modules.hephaestus, HephaestusConfig)
    assert config.modules.hephaestus.enabled is False
    assert isinstance(config.modules.hermes, HermesConfig)
    assert config.modules.hermes.enabled is False
    assert isinstance(config.modules.iris, IrisConfig)
    assert config.modules.iris.enabled is False
    assert isinstance(config.modules.kairos, KairosConfig)
