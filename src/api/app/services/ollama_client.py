"""
Async Ollama API client for LLM-powered analysis.

Wraps Ollama's /api/chat endpoint with retry logic, timeout handling,
and structured JSON response parsing.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "900"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from model output, tolerating markdown fences."""
    # Try the raw text first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip markdown code fences
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            pass

    # Greedy brace match
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except (json.JSONDecodeError, TypeError):
                        break

    return None


class OllamaClient:
    """Thin async wrapper around the Ollama HTTP API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        self.base_url = (base_url or OLLAMA_URL).rstrip("/")
        self.model = model or OLLAMA_MODEL
        self.timeout = timeout or OLLAMA_TIMEOUT
        self.max_retries = max_retries or OLLAMA_MAX_RETRIES

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        format_json: bool = True,
    ) -> Dict[str, Any]:
        """
        Send a generate completion request to Ollama.

        Messages can include optional "images" (list of base64 strings) for
        multimodal models (e.g. llava, llama3.2-vision).

        Returns the parsed JSON object when *format_json* is True, otherwise
        the raw assistant message content.
        """
        response_format = {
            "type": "object",
            "properties": {
                "threat_level": {"type": "string", "enum": ["high", "medium", "low", "benign"]},
                "confidence": {"type": "integer"},
                "summary": {"type": "string"},
                "recommended_action": {"type": "string", "enum": [
                    "takedown_requested", "monitoring", "blocked_firewall",
                    "reported_google_safe_browsing", "dismissed", "other"
                ]},
                "reasoning": {"type": "string"},
                "indicators": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["threat_level", "confidence", "summary","recommended_action", "reasoning", "indicators"],
        }
        system_prompt = messages[0]["content"]
        user_message = messages[1]["content"]
        raw_prompt = (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_message}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "prompt": raw_prompt,
            "raw": True,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 1024,
                "num_ctx": 4096,
                "num_thread": 20,
                "num_batch": 512,
            },
            "format": response_format,
        }
        logger.debug(f"Payload: {json.dumps(payload)}")
        url = f"{self.base_url}/api/generate"
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 2):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            raise RuntimeError(
                                f"Ollama returned HTTP {resp.status}: {body[:500]}"
                            )
                        data = await resp.json()
                        content = data.get("response", "")

                        #if not format_json:
                        #    return {"content": content, "model": data.get("model", self.model)}

                        parsed = _extract_json(content)
                        if parsed is None:
                            raise ValueError(
                                f"Failed to parse JSON from model output: {content[:300]}"
                            )
                        parsed["_model"] = data.get("model", self.model)
                        return parsed

            except Exception as exc:
                last_error = exc
                if attempt <= self.max_retries:
                    logger.warning(
                        "Ollama request attempt %d/%d failed: %s",
                        attempt,
                        self.max_retries + 1,
                        exc,
                    )
                    import asyncio
                    await asyncio.sleep(min(2 ** attempt, 10))

        raise RuntimeError(f"Ollama request failed after {self.max_retries + 1} attempts: {last_error}")

    async def list_models(self) -> List[Dict[str, Any]]:
        """Return the list of locally available models from Ollama."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Ollama returned HTTP {resp.status}")
                data = await resp.json()
                return data.get("models", [])

    async def health_check(self) -> bool:
        """Return True if the Ollama API is reachable."""
        try:
            await self.list_models()
            return True
        except Exception:
            return False


# Module-level singleton
ollama_client = OllamaClient()
