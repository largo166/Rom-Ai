"""
json_safety.py - JSON 字段统一安全解析 + 写入校验层
Phase 1 地基加固：防止 JSON 解析失败导致的崩溃
"""
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def safe_json_parse(raw: Any, default: Any = None, field_name: str = "") -> Any:
    """
    安全解析 JSON 字段，解析失败返回 default 而非崩溃。

    参数：
        raw: 原始值（可能是字符串、dict、list 或 None）
        default: 解析失败时的默认值（默认 None）
        field_name: 字段名，用于日志记录

    返回：
        解析后的 Python 对象，或 default
    """
    if raw is None:
        return default
    # 已经是结构化类型，直接返回
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            "JSON parse failed for field '%s': %s, returning default",
            field_name,
            e,
        )
        return default


def safe_json_dump(data: Any, field_name: str = "") -> Optional[str]:
    """
    安全序列化 JSON 字段，确保存入的是合法 JSON。

    参数：
        data: 要序列化的数据
        field_name: 字段名，用于日志记录

    返回：
        JSON 字符串，或 None（data 为 None 时）
    """
    if data is None:
        return None
    if isinstance(data, str):
        # 验证已有字符串是否合法 JSON
        try:
            json.loads(data)
            return data
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Invalid JSON string for field '%s', wrapping as string",
                field_name,
            )
            return json.dumps(data, ensure_ascii=False)
    try:
        return json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        logger.warning("JSON dump failed for field '%s': %s", field_name, e)
        return None
