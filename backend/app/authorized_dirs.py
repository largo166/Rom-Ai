"""User-managed authorized folder roots.

The desktop app is single-user, but local folder access is still explicit:
only ROM-AI managed system directories plus user-approved folders are allowed.
The approved list is stored in the local AppData-backed BASE_DIR.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import BASE_DIR


CONFIG_PATH = BASE_DIR / "authorized_dirs.json"


class AuthorizedDirError(ValueError):
    pass


def _resolve(path: str | Path) -> Path:
    try:
        return Path(path).expanduser().resolve()
    except OSError as exc:
        raise AuthorizedDirError(f"路径无法解析：{path}") from exc


def _safe_resolve(path: str | Path) -> Path | None:
    try:
        return Path(path).expanduser().resolve()
    except OSError:
        try:
            return Path(path).expanduser().absolute()
        except OSError:
            return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _blocked_roots() -> list[tuple[Path, bool]]:
    roots: list[tuple[Path, bool]] = []
    home = _safe_resolve(Path.home())
    if home:
        roots.append((home, False))
    for child in ("Desktop", "Documents", "Downloads"):
        if not home:
            continue
        candidate = home / child
        if candidate.exists():
            resolved = _safe_resolve(candidate)
            if resolved:
                roots.append((resolved, False))
    for raw, include_children in (
        ("C:/", False),
        ("C:/Windows", True),
        ("C:/Program Files", True),
        ("C:/Program Files (x86)", True),
        (str(BASE_DIR), False),
    ):
        resolved = _safe_resolve(raw)
        if resolved:
            roots.append((resolved, include_children))
    return roots


def validate_authorized_dir_candidate(path: str | Path) -> Path:
    resolved = _resolve(path)
    if not resolved.exists() or not resolved.is_dir():
        raise AuthorizedDirError(f"授权路径必须是已存在的文件夹：{resolved}")
    if resolved.is_symlink():
        raise AuthorizedDirError(f"拒绝授权符号链接文件夹：{resolved}")
    if resolved.parent == resolved:
        raise AuthorizedDirError("拒绝授权磁盘根目录")
    for blocked, include_children in _blocked_roots():
        if resolved == blocked or (include_children and _is_relative_to(resolved, blocked)):
            raise AuthorizedDirError(f"拒绝授权过宽路径：{resolved}")
    return resolved


def load_authorized_dirs() -> list[Path]:
    if not CONFIG_PATH.exists():
        return []
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = raw.get("authorized_dirs", []) if isinstance(raw, dict) else []
    resolved: list[Path] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            continue
        try:
            path = _resolve(item)
        except AuthorizedDirError:
            continue
        if path.exists() and path.is_dir() and path not in resolved:
            resolved.append(path)
    return resolved


def save_authorized_dirs(paths: list[Path]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    unique: list[str] = []
    for path in paths:
        text = str(path)
        if text not in unique:
            unique.append(text)
    CONFIG_PATH.write_text(json.dumps({"authorized_dirs": unique}, ensure_ascii=False, indent=2), encoding="utf-8")


def list_authorized_dirs() -> list[str]:
    return [str(path) for path in load_authorized_dirs()]


def add_authorized_dir(path: str | Path) -> list[str]:
    candidate = validate_authorized_dir_candidate(path)
    dirs = load_authorized_dirs()
    if candidate not in dirs:
        dirs.append(candidate)
    save_authorized_dirs(dirs)
    return list_authorized_dirs()


def remove_authorized_dir(path: str | Path) -> list[str]:
    target = _resolve(path)
    dirs = [item for item in load_authorized_dirs() if item != target and not _is_relative_to(item, target)]
    save_authorized_dirs(dirs)
    return list_authorized_dirs()
