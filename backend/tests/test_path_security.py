import pytest
from pathlib import Path
from unittest.mock import patch

from app.security import PathValidationError, get_allowed_roots, validate_path


class MockSettings:
    """用于 mock app.config.settings 的轻量对象"""

    def __init__(self, **kwargs):
        self.default_vault_path = kwargs.get("default_vault_path", "")
        self.data_dir = kwargs.get("data_dir", "")
        self.upload_root = kwargs.get("upload_root", "")
        self.authorized_dirs = kwargs.get("authorized_dirs", [])


def test_path_traversal_blocked(tmp_path):
    """路径穿越应被拦截：子目录解析后跳出授权根目录"""
    authorized_dir = tmp_path / "vault"
    authorized_dir.mkdir()
    subdir = authorized_dir / "sub"
    subdir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("evil")

    traversal_path = str(subdir / ".." / ".." / "outside.txt")
    with pytest.raises(PathValidationError):
        validate_path(traversal_path, allowed_bases=[authorized_dir], must_exist=True)


def test_unauthorized_absolute_path_blocked(tmp_path):
    """白名单外的绝对路径应被拒绝"""
    authorized_dir = tmp_path / "vault"
    authorized_dir.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    evil_file = other_dir / "evil.txt"
    evil_file.write_text("evil")

    with pytest.raises(PathValidationError):
        validate_path(str(evil_file), allowed_bases=[authorized_dir], must_exist=True)


def test_empty_path_blocked():
    """空字符串和纯空白路径应被拒绝"""
    for empty in ["", "   ", "\t\n"]:
        with pytest.raises(PathValidationError):
            validate_path(empty, allowed_bases=[Path("/tmp")])


def test_authorized_path_allowed(tmp_path):
    """授权目录内的路径应正常通过"""
    authorized_dir = tmp_path / "vault"
    authorized_dir.mkdir()
    subdir = authorized_dir / "subdir"
    subdir.mkdir()
    safe_file = subdir / "safe.txt"
    safe_file.write_text("ok")

    result = validate_path(
        str(safe_file), allowed_bases=[authorized_dir], must_exist=True
    )
    assert result == safe_file.resolve()


def test_no_allowed_roots_fail_closed(tmp_path):
    """授权目录列表为空时默认拒绝（fail-closed）"""
    authorized_dir = tmp_path / "vault"
    authorized_dir.mkdir()
    safe_file = authorized_dir / "safe.txt"
    safe_file.write_text("ok")

    with pytest.raises(PathValidationError):
        validate_path(str(safe_file), allowed_bases=[], must_exist=True)


def test_get_allowed_roots_collects_configured_dirs(tmp_path):
    """get_allowed_roots 应汇总所有已配置目录和用户授权目录"""
    vault = tmp_path / "vault"
    vault.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    upload = tmp_path / "upload"
    upload.mkdir()
    extra = tmp_path / "extra"
    extra.mkdir()

    settings = MockSettings(
        default_vault_path=str(vault),
        data_dir=str(data),
        upload_root=str(upload),
        authorized_dirs=[str(extra), ""],  # 空字符串应被跳过
    )

    with patch("app.config.get_settings", return_value=settings):
        roots = get_allowed_roots()

    assert vault.resolve() in roots
    assert data.resolve() in roots
    assert upload.resolve() in roots
    assert extra.resolve() in roots


def test_get_allowed_roots_empty_when_nothing_configured():
    """没有任何目录配置时返回空列表"""
    settings = MockSettings()
    with patch("app.config.get_settings", return_value=settings):
        roots = get_allowed_roots()
    assert roots == []
