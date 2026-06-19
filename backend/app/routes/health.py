from fastapi import APIRouter, HTTPException

from app.cloud import cloud_enabled, cloud_root_path
from app.config import BASE_DIR, ENV_FILE, LOG_DIR, settings, write_env_value
from app.schemas import DeepSeekSettingsUpdate, HealthOut, SettingsStatusOut, TencentMeetingSettingsUpdate
from app.services import list_deepseek_models

router = APIRouter()


@router.get("/api/health", response_model=HealthOut)
def health():
    return {
        "status": "ok",
        "service": "rmo-ai-backend",
        "database": "sqlite",
    }


@router.get("/api/settings/status", response_model=SettingsStatusOut)
def settings_status():
    return {
        "deepseek_configured": bool(settings.deepseek_api_key.strip()),
        "deepseek_base_url": settings.deepseek_base_url,
        "deepseek_model": settings.deepseek_model,
        "image_provider": settings.image_provider,
        "image_configured": settings.image_configured,
        "image_base_url": settings.image_base_url,
        "image_model": settings.image_model,
        "tencent_meeting_configured": bool(settings.tencent_meeting_token.strip()),
        "default_vault_path": settings.default_vault_path,
        "upload_root": str(settings.upload_root_path),
        "cloud_upload_enabled": cloud_enabled(),
        "cloud_upload_root": str(cloud_root_path()) if settings.cloud_upload_root else "",
        "mock_mode": settings.mock_mode,
        "database_url": settings.database_url,
        "data_dir": str(BASE_DIR),
        "env_file": str(ENV_FILE),
        "log_dir": str(LOG_DIR),
    }


@router.post("/api/settings/deepseek", response_model=SettingsStatusOut)
def update_deepseek_settings(payload: DeepSeekSettingsUpdate):
    next_key = payload.api_key.strip()
    if next_key:
        settings.deepseek_api_key = next_key
    settings.deepseek_base_url = payload.base_url.strip() or "https://api.deepseek.com"
    settings.deepseek_model = payload.model.strip() or "deepseek-chat"
    if next_key:
        write_env_value("DEEPSEEK_API_KEY", settings.deepseek_api_key)
    write_env_value("DEEPSEEK_BASE_URL", settings.deepseek_base_url)
    write_env_value("DEEPSEEK_MODEL", settings.deepseek_model)
    return settings_status()


@router.post("/api/settings/tencent-meeting", response_model=SettingsStatusOut)
def update_tencent_meeting_settings(payload: TencentMeetingSettingsUpdate):
    next_token = payload.token.strip()
    if next_token:
        settings.tencent_meeting_token = next_token
        write_env_value("TENCENT_MEETING_TOKEN", settings.tencent_meeting_token)
    return settings_status()


@router.get("/api/settings/deepseek/models")
async def deepseek_models():
    if settings.mock_mode:
        raise HTTPException(status_code=400, detail="请先配置 DeepSeek API Key")
    try:
        return {"models": await list_deepseek_models()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"拉取 DeepSeek 模型失败：{exc}") from exc
