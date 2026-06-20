import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(os.environ.get("ROM_AI_BASE_DIR") or Path(__file__).resolve().parents[1]).resolve()
ENV_FILE = Path(os.environ.get("ROM_AI_ENV_FILE") or BASE_DIR / ".env").resolve()
LOG_DIR = Path(os.environ.get("ROM_AI_LOG_DIR") or BASE_DIR / "logs").resolve()


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    image_provider: str = "huashu"
    image_api_key: str = ""
    image_base_url: str = "https://api.openai.com/v1"
    image_model: str = "gpt-image-1"
    image_output_dir: str = ""  # 生图输出目录，空则用项目目录下 assets/ai-generated/
    tencent_meeting_token: str = ""
    tencent_meeting_script_path: str = ""  # 腾讯会议脚本路径，空则自动探测
    meeting_script_timeout: int = 30  # 脚本执行超时(秒)
    default_vault_path: str = ""
    upload_root: str = str(BASE_DIR / "uploads")
    cloud_upload_enabled: bool = False
    cloud_upload_root: str = str(BASE_DIR / "cloud")
    database_url: str = "sqlite:///./data/rmo_ai.db"
    data_dir: str = ""
    authorized_dirs: list = []  # JSON 数组，用户动态添加的授权目录

    # 音频转写配置
    audio_provider: str = "whisper"  # whisper / tencent_cloud
    whisper_api_key: str = ""  # 若为空则使用 deepseek_api_key
    whisper_base_url: str = "https://api.openai.com/v1"
    audio_max_size_mb: int = 100
    audio_allowed_formats: str = ".wav,.mp3,.m4a,.ogg,.flac,.webm"  # 逗号分隔

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    @property
    def mock_mode(self) -> bool:
        return not bool(self.deepseek_api_key.strip())

    @property
    def image_configured(self) -> bool:
        return bool(self.image_api_key.strip())

    @property
    def upload_root_path(self) -> Path:
        path = Path(self.upload_root)
        if not path.is_absolute():
            return (BASE_DIR / path).resolve()
        return path.resolve()

    @property
    def data_dir_path(self) -> Path:
        path = Path(self.data_dir) if self.data_dir else BASE_DIR
        if not path.is_absolute():
            return (BASE_DIR / path).resolve()
        return path.resolve()


settings = Settings()


def get_settings() -> Settings:
    return settings


def write_env_value(key: str, value: str) -> None:
    env_path = ENV_FILE
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    found = False
    updated = []
    for line in lines:
        if line.startswith(f"{key}="):
            updated.append(f"{key}={value}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(f"{key}={value}")
    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
