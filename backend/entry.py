"""Rmo-AI 后端打包入口。

该文件是 PyInstaller 打包后的可执行入口，替代命令行 `uvicorn main:app`。
运行时会：
1. 解析 --port 参数；
2. 读取 RMO_DATA_DIR 环境变量，把所有数据（数据库、上传、日志、.env）写入该目录；
3. 执行 alembic 数据库迁移；
4. 启动 uvicorn 服务，仅监听 127.0.0.1。
"""
import os
import sys
from multiprocessing import freeze_support
from pathlib import Path


# Windows 非 UTF-8 终端下，强制 Python 以 UTF-8 读取 alembic.ini / 迁移脚本。
# 若调用方（如 Electron）已设置 PYTHONUTF8=1，则直接继续；否则重启自身。
if sys.platform == "win32" and os.environ.get("PYTHONUTF8") != "1":
    os.environ["PYTHONUTF8"] = "1"
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _ensure_utf8_io() -> None:
    """PyInstaller 窗口化运行时常用默认编码为 GBK，且 stdout/stderr 可能为 None。

    该函数在打包环境下：
    1. 把无编码参数的文本 open() 重定向为 UTF-8，确保 alembic 能读取中文配置/脚本；
    2. 若 stdout/stderr 为 None，则重定向到 devnull，避免 uvicorn/click/colorama 初始化崩溃。
    """
    if not getattr(sys, "frozen", False):
        return

    import builtins

    _orig_open = builtins.open

    def _open_utf8(file, mode="r", *args, **kwargs):
        if isinstance(mode, str) and "b" not in mode and kwargs.get("encoding") is None:
            kwargs["encoding"] = "utf-8"
        return _orig_open(file, mode, *args, **kwargs)

    builtins.open = _open_utf8

    if sys.stdout is None:
        sys.stdout = _orig_open(os.devnull, "w", encoding="utf-8", errors="ignore")
    if sys.stderr is None:
        sys.stderr = _orig_open(os.devnull, "w", encoding="utf-8", errors="ignore")


def _resolve_base_path() -> Path:
    """在源码/打包环境下定位项目根目录。"""
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()


def run_migrations() -> None:
    """在代码内执行 alembic upgrade head。"""
    from alembic import command
    from alembic.config import Config

    base_path = _resolve_base_path()
    alembic_ini = base_path / "alembic.ini"
    migrations_dir = base_path / "migrations"

    if not alembic_ini.exists():
        print(f"[entry] alembic.ini not found at {alembic_ini}, skipping migration", flush=True)
        return

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(migrations_dir))
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")
    print("[entry] Alembic upgrade head completed", flush=True)


def _parse_port(args: list[str]) -> int:
    """从命令行参数解析 --port。"""
    port = 8000
    for i, arg in enumerate(args[1:], start=1):
        if arg == "--port" and i < len(args) - 1:
            try:
                port = int(args[i + 1])
            except ValueError:
                pass
    return port


def _configure_data_dir(data_dir: Path) -> None:
    """把数据目录写入环境变量，供 app.config 与数据库使用。"""
    data_dir = data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    uploads_dir = data_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    cloud_dir = data_dir / "cloud"
    cloud_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "rmo_ai.db"
    env_path = data_dir / ".env"

    # 任务要求的 RMO_* 变量（供日志/外部工具读取）
    os.environ.setdefault("RMO_DATA_DIR", str(data_dir))
    os.environ.setdefault("RMO_DB_PATH", str(db_path))
    os.environ.setdefault("RMO_UPLOAD_DIR", str(uploads_dir))
    os.environ.setdefault("RMO_LOG_DIR", str(logs_dir))

    # 项目现有配置读取的变量（必须在 import app 前设置）
    os.environ["ROM_AI_BASE_DIR"] = str(data_dir)
    os.environ["ROM_AI_ENV_FILE"] = str(env_path)
    os.environ["ROM_AI_LOG_DIR"] = str(logs_dir)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["UPLOAD_ROOT"] = str(uploads_dir)
    os.environ["CLOUD_UPLOAD_ROOT"] = str(cloud_dir)


def main() -> None:
    freeze_support()
    _ensure_utf8_io()

    port = _parse_port(sys.argv)

    data_dir_env = os.environ.get("RMO_DATA_DIR", "")
    if data_dir_env:
        _configure_data_dir(Path(data_dir_env))

    # 先迁移，再启动服务
    try:
        run_migrations()
    except Exception as exc:  # noqa: BLE001
        print(f"[entry] Migration failed (non-fatal): {exc}", flush=True)

    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        log_config=None,
    )


if __name__ == "__main__":
    main()
