from __future__ import annotations

import logging

from hestia.config import HestiaConfig, StrictConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.base import HestiaModule
from hestia.modules.kairos.module import KairosModule
from hestia.modules.zephyrus.module import ZephyrusModule

logger = logging.getLogger(__name__)

MODULE_REGISTRY: dict[str, type[HestiaModule]] = {
    "zephyrus": ZephyrusModule,
    "kairos": KairosModule,
}


async def load_modules(
    config: HestiaConfig,
    registry: ToolRegistry,
) -> list[HestiaModule]:
    module_configs: dict[str, StrictConfig] = {
        "zephyrus": config.modules.zephyrus,
        "kairos": config.modules.kairos,
    }
    if set(MODULE_REGISTRY) != set(module_configs):
        raise RuntimeError("Every registered module must have typed configuration")

    loaded: list[HestiaModule] = []
    for slug, module_cls in MODULE_REGISTRY.items():
        module_config = module_configs[slug]
        if not getattr(module_config, "enabled", False):
            logger.info("Module %s is disabled", slug)
            continue
        module = module_cls()
        if not isinstance(module_config, module.config_type):
            raise TypeError(f"Configuration type mismatch for module {slug}")
        try:
            await module.setup(module_config)
            registry.register_module(module)
        except Exception:
            logger.exception("Module %s failed to load", slug)
            await module.teardown()
            continue
        loaded.append(module)
        logger.info("Loaded module %s (%s)", module.display_name, slug)
    return loaded


async def teardown_modules(modules: list[HestiaModule]) -> None:
    for module in reversed(modules):
        try:
            await module.teardown()
        except Exception:
            logger.exception("Module %s failed during teardown", module.slug)
