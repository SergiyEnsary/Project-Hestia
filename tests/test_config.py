import pytest
import yaml
from pydantic import ValidationError

from hestia.config import HestiaConfig, _resolve_env, load_config


def test_resolve_env_substitution(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "resolved-value")
    assert _resolve_env("${MY_SECRET}") == "resolved-value"
    assert _resolve_env({"key": "${MY_SECRET}"}) == {"key": "resolved-value"}


def test_load_config_from_tmp_path(tmp_path, monkeypatch):
    config_data = {
        "llm": {"model": "test-model"},
        "modules": {"zephyrus": {"enabled": False}},
    }
    (tmp_path / "config.yaml").write_text(yaml.dump(config_data), encoding="utf-8")
    (tmp_path / ".env").write_text("HESTIA_API_TOKEN=from-env-file\n", encoding="utf-8")
    monkeypatch.setenv("HESTIA_CONFIG", str(tmp_path / "config.yaml"))
    monkeypatch.delenv("HESTIA_API_TOKEN", raising=False)

    config = load_config()
    assert config.api_token == "from-env-file"
    assert config.llm.model == "test-model"
    assert config.modules.zephyrus.enabled is False


def test_load_config_env_overrides_stale_shell(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("llm:\n  model: m1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("HESTIA_API_TOKEN=file-token\n", encoding="utf-8")
    monkeypatch.setenv("HESTIA_CONFIG", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("HESTIA_API_TOKEN", "stale-shell-token")

    config = load_config()
    assert config.api_token == "file-token"


def test_hestia_config_defaults():
    config = HestiaConfig()
    assert config.llm.provider == "ollama"
    assert config.security.require_auth is True
    assert config.server.host == "127.0.0.1"


def test_config_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        HestiaConfig(security={"require_auth": True, "unknown": "value"})


def test_remote_bind_requires_strong_authentication():
    config = HestiaConfig(
        server={"host": "0.0.0.0"},
        api_token="short",
    )
    with pytest.raises(ValueError, match="32 characters"):
        config.validate_runtime_safety()


def test_remote_llm_requires_explicit_secure_transport():
    with pytest.raises(ValidationError, match="allow_remote"):
        HestiaConfig(llm={"base_url": "https://llm.example"})
    with pytest.raises(ValidationError, match="allow_insecure_http"):
        HestiaConfig(
            llm={
                "base_url": "http://host.docker.internal:11434",
                "allow_remote": True,
            }
        )
