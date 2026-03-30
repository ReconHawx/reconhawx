"""
AI infrastructure routes.

Generic endpoints for LLM service management (model listing, health checks)
that are shared across all AI-powered features in the application.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user_from_middleware
from models.user_postgres import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/models", response_model=Dict[str, Any])
async def list_models(
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """List available Ollama models and the configured default."""
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
        return {
            "status": "success",
            "default_model": ollama_client.model,
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
