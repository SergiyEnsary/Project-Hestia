from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return normalized == "localhost"


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMConfig(StrictConfig):
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1:8b"
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    allow_remote: bool = False
    allow_insecure_http: bool = False

    @model_validator(mode="after")
    def validate_base_url(self) -> LLMConfig:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("llm.base_url must be an HTTP(S) URL")
        if not _is_loopback_host(parsed.hostname):
            if not self.allow_remote:
                raise ValueError("Remote LLM endpoints require llm.allow_remote=true")
            if parsed.scheme != "https" and not self.allow_insecure_http:
                raise ValueError("Remote HTTP LLM endpoints require llm.allow_insecure_http=true")
        return self


class SecurityConfig(StrictConfig):
    require_auth: bool = True
    rate_limit_per_minute: int = Field(default=30, ge=1, le=1000)
    max_message_length: int = Field(default=4000, ge=1, le=100_000)
    max_tool_iterations: int = Field(default=10, ge=1, le=50)
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("At least one allowed origin is required")
        for value in values:
            parsed = urlsplit(value)
            if value == "*" or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Invalid allowed origin: {value}")
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("Allowed origins cannot include paths, queries, or fragments")
        return list(dict.fromkeys(value.rstrip("/") for value in values))


class ServerConfig(StrictConfig):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class AWSBackupConfig(StrictConfig):
    enabled: bool = False
    s3_bucket: str = ""


class AWSLLMFallbackConfig(StrictConfig):
    enabled: bool = False
    provider: str = "bedrock"
    model: str = ""


class AWSConfig(StrictConfig):
    enabled: bool = False
    region: str = "us-east-1"
    secrets_provider: str = "env"
    backup: AWSBackupConfig = Field(default_factory=AWSBackupConfig)
    llm_fallback: AWSLLMFallbackConfig = Field(default_factory=AWSLLMFallbackConfig)


class ZephyrusConfig(StrictConfig):
    enabled: bool = True
    default_location: str = Field(default="San Francisco", min_length=1, max_length=200)
    units: str = "metric"

    @field_validator("units")
    @classmethod
    def validate_units(cls, value: str) -> str:
        if value not in {"metric", "imperial"}:
            raise ValueError("units must be 'metric' or 'imperial'")
        return value


class KairosConfig(StrictConfig):
    enabled: bool = False
    source: str = "ical"
    ical_url: str = Field(default="", repr=False)
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    max_response_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    allow_private_hosts: bool = False

    @model_validator(mode="after")
    def validate_enabled_source(self) -> KairosConfig:
        if self.source != "ical":
            raise ValueError("Kairos currently supports only the 'ical' source")
        if self.enabled and not self.ical_url:
            raise ValueError("modules.kairos.ical_url is required when Kairos is enabled")
        return self


class ModulesConfig(StrictConfig):
    zephyrus: ZephyrusConfig = Field(default_factory=ZephyrusConfig)
    kairos: KairosConfig = Field(default_factory=KairosConfig)


class PythiaConfig(StrictConfig):
    enabled: bool = True


class EchoConfig(StrictConfig):
    enabled: bool = False
    stt_model_path: Path | None = None
    tts_model_path: Path | None = None
    language: str = Field(default="en", min_length=2, max_length=16)
    compute_type: str = Field(default="int8", min_length=1, max_length=32)
    max_audio_bytes: int = Field(default=10_000_000, ge=1024, le=50_000_000)
    max_audio_seconds: int = Field(default=30, ge=1, le=300)
    max_tts_characters: int = Field(default=2000, ge=1, le=10_000)
    max_tts_audio_bytes: int = Field(default=15_000_000, ge=1024, le=50_000_000)
    rate_limit_per_minute: int = Field(default=6, ge=1, le=60)

    @model_validator(mode="after")
    def validate_model_paths(self) -> EchoConfig:
        if self.enabled and (self.stt_model_path is None or self.tts_model_path is None):
            raise ValueError(
                "interfaces.echo.stt_model_path and tts_model_path are required "
                "when Echo is enabled"
            )
        return self


class InterfacesConfig(StrictConfig):
    pythia: PythiaConfig = Field(default_factory=PythiaConfig)
    echo: EchoConfig = Field(default_factory=EchoConfig)


class MnemosyneConfig(StrictConfig):
    backend: str = "memory"
    database_path: Path = Path(".hestia/mnemosyne.db")
    retention_days: int = Field(default=30, ge=1, le=3650)
    max_messages_per_session: int = Field(default=200, ge=2, le=10_000)

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        if value not in {"memory", "sqlite"}:
            raise ValueError("mnemosyne.backend must be 'memory' or 'sqlite'")
        return value


class HestiaConfig(StrictConfig):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    modules: ModulesConfig = Field(default_factory=ModulesConfig)
    interfaces: InterfacesConfig = Field(default_factory=InterfacesConfig)
    mnemosyne: MnemosyneConfig = Field(default_factory=MnemosyneConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    api_token: str = Field(default="", repr=False)

    @property
    def pythia_dist(self) -> Path:
        return Path(__file__).resolve().parent / "interfaces" / "pythia" / "dist"

    def validate_runtime_safety(self) -> None:
        if _is_loopback_host(self.server.host):
            return
        if not self.security.require_auth:
            raise ValueError("Authentication is required when binding beyond loopback")
        if len(self.api_token) < 32:
            raise ValueError(
                "HESTIA_API_TOKEN must contain at least 32 characters when binding beyond loopback"
            )


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
    raise FileNotFoundError("No config.yaml found. Copy config.yaml.example to config.yaml")


def load_config() -> HestiaConfig:
    config_path = _find_config_path()
    env_path = config_path.parent / ".env"
    # .env next to config.yaml is the source of truth (overrides stale shell exports)
    load_dotenv(env_path, override=True)
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    raw = _resolve_env(raw)
    server = raw.setdefault("server", {})
    if host := os.environ.get("HESTIA_HOST"):
        server["host"] = host
    if port := os.environ.get("HESTIA_PORT"):
        server["port"] = int(port)
    api_token = os.environ.get("HESTIA_API_TOKEN", "")
    config = HestiaConfig(api_token=api_token, **raw)
    if not config.mnemosyne.database_path.is_absolute():
        config.mnemosyne.database_path = (
            config_path.parent / config.mnemosyne.database_path
        ).resolve()
    echo = config.interfaces.echo
    if echo.stt_model_path is not None and not echo.stt_model_path.is_absolute():
        echo.stt_model_path = (config_path.parent / echo.stt_model_path).resolve()
    if echo.tts_model_path is not None and not echo.tts_model_path.is_absolute():
        echo.tts_model_path = (config_path.parent / echo.tts_model_path).resolve()
    return config
