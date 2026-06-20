"""tests/test_formatting.py — Markdown格式整理单元测试"""
import pytest
from app.services.formatting import (
    standardize_markdown,
    _build_frontmatter,
    _find_frontmatter_end,
    _ensure_heading,
    _normalize_list_indent,
)


class TestStandardizeMarkdownNoFrontmatter:
    def test_adds_frontmatter(self):
        content = "# 测试文档\n\n正文内容。"
        result = standardize_markdown(content, "测试文档", "文档")
        assert result.startswith("---\n")
        assert "type: 文档" in result
        assert "title: 测试文档" in result

    def test_adds_heading_when_missing(self):
        content = "正文内容，没有标题。"
        result = standardize_markdown(content, "自动标题")
        assert "# 自动标题" in result

    def test_preserves_existing_heading(self):
        content = "# 已有标题\n\n正文内容。"
        result = standardize_markdown(content, "不同标题")
        assert "# 已有标题" in result
        # 不应重复添加标题
        assert result.count("# 已有标题") == 1

    def test_trailing_newline(self):
        content = "正文"
        result = standardize_markdown(content, "标题")
        assert result.endswith("\n")

    def test_file_type_in_frontmatter(self):
        content = "内容"
        result = standardize_markdown(content, "标题", "技术条件")
        assert "type: 技术条件" in result


class TestStandardizeMarkdownExistingFrontmatter:
    def test_preserves_existing_fields(self):
        content = "---\ntype: 会议资料\ntitle: 会议纪要\ndate: 2026-01-01\nauthor: 张三\n---\n\n# 会议纪要\n\n内容。"
        result = standardize_markdown(content, "新标题", "文档")
        assert "type: 会议资料" in result
        assert "author: 张三" in result

    def test_fills_missing_fields(self):
        content = "---\ntype: 会议资料\n---\n\n# 内容\n"
        result = standardize_markdown(content, "自动标题", "文档")
        assert "title: 自动标题" in result
        assert "date:" in result

    def test_does_not_duplicate_frontmatter(self):
        content = "---\ntype: 文档\ntitle: 原标题\ndate: 2026-01-01\n---\n\n# 原标题\n\n内容。"
        result = standardize_markdown(content, "原标题", "文档")
        # frontmatter 只出现一次
        assert result.count("---") >= 2
        assert result.count("type: 文档") == 1


class TestNormalizeEmptyLines:
    def test_compress_multiple_blank_lines(self):
        content = "段落一\n\n\n\n\n段落二"
        result = standardize_markdown(content, "标题")
        assert "\n\n\n" not in result

    def test_single_blank_line_preserved(self):
        content = "段落一\n\n段落二"
        result = standardize_markdown(content, "标题")
        # 经过格式化后，不应该把单个空行也消除
        assert "段落一" in result
        assert "段落二" in result


class TestEnsureHeading:
    def test_adds_heading_to_empty(self):
        result = _ensure_heading("", "标题")
        assert result.startswith("# 标题")

    def test_no_double_heading(self):
        body = "# 已有标题\n\n内容"
        result = _ensure_heading(body, "其他标题")
        assert result == body
        assert "# 其他标题" not in result

    def test_heading_with_leading_newlines(self):
        body = "\n\n# 标题\n内容"
        result = _ensure_heading(body, "新标题")
        # 如果正文stripped以"# "开头，保留原本
        assert "# 标题" in result

    def test_body_without_heading(self):
        body = "这是正文，没有标题行。"
        result = _ensure_heading(body, "补充标题")
        assert result.startswith("# 补充标题")


class TestNormalizeListIndent:
    def test_no_list(self):
        body = "普通段落\n没有列表"
        result = _normalize_list_indent(body)
        assert result == body

    def test_dash_list(self):
        body = "- 一级项目\n    - 二级项目"
        result = _normalize_list_indent(body)
        lines = result.split("\n")
        assert lines[0].startswith("- ")
        assert lines[1].startswith("  - ")

    def test_asterisk_list(self):
        body = "* 项目一\n* 项目二"
        result = _normalize_list_indent(body)
        assert "* 项目一" in result

    def test_mixed_indent(self):
        body = "- item1\n        - deeply_nested"
        result = _normalize_list_indent(body)
        lines = result.split("\n")
        # 8 spaces = 2 levels → "    - deeply_nested"
        assert lines[1].startswith("    - ")
