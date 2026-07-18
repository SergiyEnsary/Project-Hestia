from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1:8b"
    timeout_seconds: int = 120


class SecurityConfig(BaseModel):
    require_auth: bool = True
    rate_limit_per_minute: int = 30
    max_message_length: int = 4000
    max_tool_iterations: int = 10
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class AWSConfig(BaseModel):
    enabled: bool = False
    region: str = "us-east-1"
    secrets_provider: str = "env"


class HestiaConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    modules: dict[str, dict[str, Any]] = Field(default_factory=dict)
    interfaces: dict[str, dict[str, Any]] = Field(default_factory=dict)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    api_token: str = ""

    @property
    def pythia_dist(self) -> Path:
        return Path(__file__).resolve().parent / "interfaces" / "pythia" / "dist"


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):

        def replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            return os.environ.get(key, "")

        return _ENV_PATTERN.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def _find_config_path() -> Path:
    candidates = [
        Path(os.environ.get("HESTIA_CONFIG", "")),
        Path.cwd() / "config.yaml",
        Path(__file__).resolve().parent.parent / "config.yaml",
    ]
    for path in candidates:
        if path and path.is_file():
            return path
    example = Path.cwd() / "config.yaml.example"
    if example.is_file():
        return example
    raise FileNotFoundError(
        "No config.yaml found. Copy config.yaml.example to config.yaml"
    )


def load_config() -> HestiaConfig:
    config_path = _find_config_path()
    env_path = config_path.parent / ".env"
    # .env next to config.yaml is the source of truth (overrides stale shell exports)
    load_dotenv(env_path, override=True)
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    raw = _resolve_env(raw)
    api_token = os.environ.get("HESTIA_API_TOKEN", "")
    return HestiaConfig(api_token=api_token, **raw)
