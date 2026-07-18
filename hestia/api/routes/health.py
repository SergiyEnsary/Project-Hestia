import httpx
from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    config = request.app.state.config
    ollama_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{config.llm.base_url.rstrip('/')}/api/tags")
            ollama_status = "ok" if response.status_code == 200 else "error"
    except (httpx.HTTPError, OSError):
        ollama_status = "unreachable"

    return {
        "status": "ok",
        "service": "hestia",
        "ollama": ollama_status,
    }
