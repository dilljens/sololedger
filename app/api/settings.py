"""LLM settings routes."""
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .deps import _DATA_DIR, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1")

_llm_settings_path: Optional[Path] = None


def _get_llm_settings_path():
    global _llm_settings_path
    if _llm_settings_path is None:
        try:
            cfg = get_config()
            _llm_settings_path = cfg.project_root / "llm_settings.json"
        except Exception as e:
            import sys
            print(f"⚠ Could not resolve LLM settings path: {e}", file=sys.stderr)
            _llm_settings_path = _DATA_DIR / "llm_settings.json"
    return _llm_settings_path


class LlmSettingsRequest(BaseModel):
    api_key: Optional[str] = None
    backend: Optional[str] = None
    model: Optional[str] = None


@router.get("/settings/llm", dependencies=[Depends(check_auth)])
async def get_llm_settings():
    settings_path = _get_llm_settings_path()
    config = {}
    if settings_path.exists():
        try:
            config = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            import sys
            print(f"⚠ Failed to read LLM settings: {e}", file=sys.stderr)

    key = config.get("api_key", "")
    if key and len(key) > 8:
        config["api_key"] = key[:8] + "••••••••••"
    elif key:
        config["api_key"] = "••••••••••"

    return _ok({
        "backend": config.get("backend", os.environ.get("SL_LLM_BACKEND", "openai")),
        "model": config.get("model", os.environ.get("SL_LLM_MODEL", "")),
        "api_key_configured": bool(config.get("api_key") or os.environ.get("SL_LLM_API_KEY")),
        "api_key": config.get("api_key", ""),
    })


@router.post("/settings/llm", dependencies=[Depends(check_auth)])
async def set_llm_settings(req: LlmSettingsRequest):
    settings_path = _get_llm_settings_path()
    config = {}
    if settings_path.exists():
        try:
            config = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            import sys
            print(f"⚠ Failed to read LLM settings for update: {e}", file=sys.stderr)

    if req.api_key is not None:
        config["api_key"] = req.api_key if req.api_key else ""
    if req.backend is not None:
        config["backend"] = req.backend
    if req.model is not None:
        config["model"] = req.model if req.model else ""

    settings_path.write_text(json.dumps(config, indent=2))

    return _ok({
        "saved": True,
        "backend": config.get("backend", "openai"),
        "model": config.get("model", ""),
        "api_key_configured": bool(config.get("api_key")),
    })
