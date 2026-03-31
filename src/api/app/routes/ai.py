"""
AI infrastructure routes.

Generic endpoints for LLM service management (model listing, health checks)
that are shared across all AI-powered features in the application.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user_from_middleware, require_superuser_or_admin
from models.user_postgres import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _ollama_tag_names(raw_models: List[Dict[str, Any]]) -> Set[str]:
    names: Set[str] = set()
    for m in raw_models:
        n = (m.get("name") or m.get("model") or "").strip()
        if n:
            names.add(n)
    return names


@router.get("/models", response_model=Dict[str, Any])
async def list_models(
    current_user: UserResponse = Depends(require_superuser_or_admin),
):
    """List available Ollama models and the configured default if that model is installed."""
    from services.ollama_client import ollama_client
    try:
        raw_models = await ollama_client.list_models()
        models = [
            {
                "name": m.get("name", m.get("model", "")),
                "size": m.get("size"),
                "parameter_size": (m.get("details") or {}).get("parameter_size"),
                "quantization": (m.get("details") or {}).get("quantization_level"),
            }
            for m in raw_models
        ]
        available = _ollama_tag_names(raw_models)
        configured = (ollama_client.model or "").strip()
        default_model: Optional[str] = configured if configured in available else None
        return {
            "status": "success",
            "default_model": default_model,
            "models": models,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to fetch models from Ollama: {exc}")


@router.get("/prompts/defaults", response_model=Dict[str, Any])
async def get_default_prompts(
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Return the default prompts for each AI-powered feature (from system settings with fallback)."""
    from services.ai_analysis_service import get_ai_settings, DEFAULT_TYPOSQUAT_PROMPT
    settings = await get_ai_settings()
    typosquat = settings.get("typosquat", {})
    return {
        "status": "success",
        "prompts": {
            "typosquat": typosquat.get("default_prompt", DEFAULT_TYPOSQUAT_PROMPT),
        },
    }


@router.get("/health", response_model=Dict[str, Any])
async def health_check(
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """Check if the Ollama AI service is reachable."""
    from services.ollama_client import ollama_client
    healthy = await ollama_client.health_check()
    return {
        "status": "healthy" if healthy else "unavailable",
        "ollama_url": ollama_client.base_url,
        "default_model": ollama_client.model,
    }
