"""
security.py - 路径安全校验工具
Phase 1 地基加固：防止路径穿越和 symlink 逃逸
"""
from pathlib import Path
from typing import Optional, List


class PathValidationError(Exception):
    pass


def validate_path(
    path: str,
    allowed_bases: Optional[List[Path]] = None,
    allow_symlinks: bool = False,
    must_exist: bool = False,
) -> Path:
    """
    安全校验路径：
      resolve → 白名单 is_relative_to → 拒绝 symlink 逃逸 → 空目录 fail closed

    参数：
        path: 待校验路径字符串
        allowed_bases: 允许的根目录白名单列表；None 表示不限制基目录
        allow_symlinks: 是否允许符号链接（默认拒绝）
        must_exist: 是否要求路径必须存在（默认不要求）

    返回：
        Path 对象（已 resolve）

    异常：
        PathValidationError: 校验失败时抛出
    """
    # 空路径 fail closed
    if not str(path).strip():
        raise PathValidationError("Empty path not allowed")

    raw = Path(path)

    # 拒绝 symlink 逃逸（resolve 之前检查原始路径）
    if not allow_symlinks and raw.is_symlink():
        raise PathValidationError(f"Symlink not allowed: {path}")

    resolved = raw.resolve()

    # 白名单校验（空列表 = fail closed，None = 不限制）
    if allowed_bases is not None:
        if not allowed_bases:
            raise PathValidationError("No allowed bases configured")
        if not any(
            resolved == base.resolve() or _is_relative_to(resolved, base.resolve())
            for base in allowed_bases
        ):
            raise PathValidationError(
                f"Path {resolved} is not within allowed bases: "
                + ", ".join(str(b) for b in allowed_bases)
            )

    # 存在性检查
    if must_exist and not resolved.exists():
        raise PathValidationError(f"Path does not exist: {resolved}")

    return resolved


def _is_relative_to(path: Path, base: Path) -> bool:
    """兼容 Python 3.8 的 is_relative_to 实现"""
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def get_allowed_roots(settings=None) -> list:
    """
    构建授权根目录列表。
    桌面端：从 settings 读取所有已配置的目录（default_vault_path, data_dir, upload_root, authorized_dirs）
    平台端预留：改为按 user_id/project_id 查 DB
    """
    from app.config import get_settings

    if settings is None:
        settings = get_settings()

    roots = []
    # 已配置的系统目录
    if settings.default_vault_path:
        roots.append(Path(settings.default_vault_path))
    if hasattr(settings, "data_dir") and settings.data_dir:
        roots.append(Path(settings.data_dir))
    if hasattr(settings, "upload_root") and settings.upload_root:
        roots.append(Path(settings.upload_root))

    # 用户动态添加的授权目录
    if hasattr(settings, "authorized_dirs") and settings.authorized_dirs:
        for d in settings.authorized_dirs:
            if d and d.strip():
                roots.append(Path(d))

    # 规范化：resolve 每个根目录
    resolved = []
    for r in roots:
        try:
            resolved.append(r.expanduser().resolve())
        except (OSError, RuntimeError):
            continue

    return resolved
