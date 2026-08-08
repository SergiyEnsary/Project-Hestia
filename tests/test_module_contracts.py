import ast
import inspect
from pathlib import Path

from jsonschema import Draft202012Validator

from hestia.config import HestiaConfig, StrictConfig
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.base import HestiaModule
from hestia.modules.loader import MODULE_REGISTRY


def test_registered_modules_satisfy_contract():
    config = HestiaConfig()
    configured_slugs = set(type(config.modules).model_fields)
    assert set(MODULE_REGISTRY) == configured_slugs

    registry = ToolRegistry()
    tool_names: set[str] = set()
    for slug, module_type in MODULE_REGISTRY.items():
        assert issubclass(module_type, HestiaModule)
        assert module_type.slug == slug
        assert module_type.display_name.strip()
        assert module_type.domain.strip()
        assert issubclass(module_type.config_type, StrictConfig)
        assert inspect.iscoroutinefunction(module_type.setup)
        assert inspect.iscoroutinefunction(module_type.teardown)

        module = module_type()
        registry.register_module(module)
        for tool in module.get_tools():
            assert tool.definition.name.startswith(f"{slug}.")
            assert tool.definition.name not in tool_names
            tool_names.add(tool.definition.name)
            Draft202012Validator.check_schema(tool.definition.parameters)
            assert tool.definition.parameters["type"] == "object"
            assert tool.definition.parameters["additionalProperties"] is False


def test_modules_do_not_import_each_other():
    modules_root = Path(__file__).resolve().parents[1] / "hestia" / "modules"
    for module_path in modules_root.glob("*/module.py"):
        slug = module_path.parent.name
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if node.module.startswith("hestia.modules.") and not node.module.startswith(
                f"hestia.modules.{slug}"
            ):
                assert node.module == "hestia.modules.base"
