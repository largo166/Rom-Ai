from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, TypeVar

from app.config import BASE_DIR, settings

T = TypeVar("T")
WRITE_LOCK = RLock()


def safe_json_loads(value: Any, default: T) -> T:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value if isinstance(value, type(default)) else default  # type: ignore[return-value]
    if not isinstance(value, str):
        return default
    text = value.strip()
    if not text:
        return default
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def safe_json_dumps(value: Any, default: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(default, ensure_ascii=False)


def ensure_json_text(value: Any, default: Any) -> str:
    parsed = safe_json_loads(value, default)
    return safe_json_dumps(parsed, default)


def commit_with_retry(db: Any, *, attempts: int = 3, base_delay: float = 0.08) -> None:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with WRITE_LOCK:
                db.commit()
            return
        except Exception as exc:
            last_exc = exc
            message = str(exc).lower()
            if "database is locked" not in message and not isinstance(exc, sqlite3.OperationalError):
                raise
            try:
                db.rollback()
            except Exception:
                pass
            time.sleep(base_delay * (2**attempt))
    if last_exc:
        raise last_exc


def _candidate_roots(extra_roots: Iterable[Path] = ()) -> list[Path]:
    from app.authorized_dirs import load_authorized_dirs

    roots = [BASE_DIR, settings.upload_root_path, Path(tempfile.gettempdir())]
    roots.extend(load_authorized_dirs())
    roots.extend(extra_roots)
    resolved: list[Path] = []
    for root in roots:
        try:
            path = Path(root).expanduser().resolve()
        except OSError:
            path = Path(root).expanduser().absolute()
        if path not in resolved:
            resolved.append(path)
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_symlink_component(path: Path) -> bool:
    current = path.anchor and Path(path.anchor) or Path()
    for part in path.parts[len(current.parts) :]:
        current = current / part
        try:
            if current.exists() and current.is_symlink():
                return True
        except OSError:
            return True
    return False


def validate_path(
    raw_path: str | Path,
    *,
    must_exist: bool = True,
    must_be_dir: bool = False,
    allow_empty: bool = False,
    extra_roots: Iterable[Path] = (),
) -> Path:
    if raw_path is None or str(raw_path).strip() == "":
        if allow_empty:
            return Path()
        raise ValueError("路径不能为空")

    raw = Path(raw_path).expanduser()
    if _has_symlink_component(raw):
        raise ValueError(f"拒绝使用符号链接路径：{raw_path}")

    try:
        path = raw.resolve()
    except OSError as exc:
        raise ValueError(f"路径无法解析：{raw_path}") from exc

    roots = _candidate_roots(extra_roots)
    if not any(_is_relative_to(path, root) or path == root for root in roots):
        allowed = "；".join(str(root) for root in roots)
        raise ValueError(f"路径不在允许范围内：{path}。允许范围：{allowed}")

    if must_exist and not path.exists():
        raise FileNotFoundError(f"路径不存在：{path}")
    if must_be_dir and path.exists() and not path.is_dir():
        raise ValueError(f"路径不是文件夹：{path}")
    return path


def validate_directory(raw_path: str | Path, *, extra_roots: Iterable[Path] = ()) -> Path:
    path = validate_path(raw_path, must_exist=True, must_be_dir=True, extra_roots=extra_roots)
    if not any(path.iterdir()):
        raise ValueError(f"文件夹为空：{path}")
    return path
