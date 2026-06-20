"""
腾讯会议集成（增强层）
路径可配置/可发现 + 优雅降级 + 超时 + 友好报错
"""
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MeetingScriptStatus:
    """腾讯会议脚本状态"""

    def __init__(self) -> None:
        self.available = False
        self.script_path: Optional[str] = None
        self.error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "script_path": self.script_path,
            "error_message": self.error_message,
        }


def discover_meeting_script(configured_path: str = "") -> MeetingScriptStatus:
    """
    探测腾讯会议脚本是否可用
    优先级：配置路径 → Electron extraResources → 开发环境相对路径
    """
    status = MeetingScriptStatus()

    candidates = []

    # 1. 配置指定路径
    if configured_path:
        candidates.append(Path(configured_path))

    # 2. Electron extraResources 约定路径
    app_path = os.environ.get("ELECTRON_APP_PATH", "")
    if app_path:
        candidates.append(Path(app_path) / "resources" / "scripts" / "tencent_meeting.py")

    # 3. 开发环境相对路径
    candidates.append(Path(__file__).parent.parent / "scripts" / "tencent_meeting.py")
    candidates.append(Path(__file__).parent.parent.parent / "scripts" / "tencent_meeting.py")

    for path in candidates:
        if path.exists() and path.is_file():
            status.available = True
            status.script_path = str(path)
            logger.info("腾讯会议脚本发现: %s", path)
            return status

    status.available = False
    status.error_message = (
        "腾讯会议脚本未找到。请在设置页配置 tencent_meeting_script_path，"
        "或将脚本放置在 scripts/ 目录下。"
    )
    logger.warning(status.error_message)
    return status


def run_meeting_script(
    script_path: str,
    action: str,
    params: Dict[str, Any],
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    执行腾讯会议脚本（带超时保护）
    """
    if not script_path or not Path(script_path).exists():
        return {
            "success": False,
            "error": "script_missing",
            "message": "腾讯会议脚本不存在，请检查配置",
        }

    try:
        cmd = ["python", script_path, action]
        for k, v in params.items():
            cmd.extend([f"--{k}", str(v)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )

        if result.returncode == 0:
            return {"success": True, "output": result.stdout}
        else:
            return {
                "success": False,
                "error": "execution_error",
                "message": f"脚本执行失败: {result.stderr[:500]}",
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "timeout",
            "message": f"脚本执行超时（{timeout}秒），已终止",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "python_not_found",
            "message": "Python 解释器未找到",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "error": "unknown",
            "message": f"执行异常: {str(e)}",
        }
