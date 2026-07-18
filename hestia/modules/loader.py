from __future__ import annotations

import logging
from typing import Any

from hestia.config import HestiaConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.zephyrus.module import ZephyrusModule

logger = logging.getLogger(__name__)

MODULE_REGISTRY: dict[str, type] = {
    "zephyrus": ZephyrusModule,
}


async def load_modules(config: HestiaConfig, registry: ToolRegistry) -> list[Any]:
    loaded = []
    for slug, module_cls in MODULE_REGISTRY.items():
        module_config = config.modules.get(slug, {})
        if not module_config.get("enabled", False):
            logger.info("Module %s is disabled", slug)
            continue
        module = module_cls()
        await module.setup(module_config)
        registry.register_module(module)
        loaded.append(module)
        logger.info("Loaded module %s (%s)", module.display_name, slug)
    return loaded


async def teardown_modules(modules: list[Any]) -> None:
    for module in modules:
        await module.teardown()
