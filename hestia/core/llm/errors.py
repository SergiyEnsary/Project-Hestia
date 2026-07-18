from __future__ import annotations


class OllamaUnavailableError(Exception):
    """Raised when Hestia cannot reach the Ollama API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        super().__init__(
            "Cannot connect to Ollama. "
            "Install Ollama from https://ollama.com, start it, then run: ollama pull llama3.1:8b"
        )
