"""项目统一时间工具。"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间（aware datetime）。"""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """返回 ISO 格式 UTC 时间字符串（带 +00:00 后缀）。"""
    return datetime.now(timezone.utc).isoformat()
