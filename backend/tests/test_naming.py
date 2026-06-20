"""tests/test_naming.py — 命名模板引擎单元测试"""
import pytest
from app.services.naming import (
    generate_standard_name,
    batch_rename_plan,
    detect_naming_conflicts,
    _sanitize,
)


class TestGenerateStandardName:
    def test_basic(self):
        name = generate_standard_name("保利市庄", "技术条件", "20260610", 1, ".md")
        assert name == "保利市庄-技术条件-20260610-001.md"

    def test_seq_padding(self):
        name = generate_standard_name("项目A", "文档", "20260101", 5, ".pdf")
        assert name == "项目A-文档-20260101-005.pdf"

    def test_seq_large(self):
        name = generate_standard_name("项目A", "文档", "20260101", 100, ".pdf")
        assert name == "项目A-文档-20260101-100.pdf"

    def test_ext_without_dot(self):
        name = generate_standard_name("ProjectX", "Report", "20260101", 1, "docx")
        assert name.endswith(".docx")

    def test_no_ext(self):
        name = generate_standard_name("ProjectX", "Report", "20260101", 1)
        assert not name.endswith(".")
        assert "ProjectX" in name

    def test_auto_date(self):
        from datetime import datetime
        name = generate_standard_name("项目A", "文档", seq=1, ext=".md")
        today = datetime.now().strftime("%Y%m%d")
        assert today in name


class TestBatchRenamePlan:
    def test_single_file(self):
        files = [{"id": "1", "filename": "test.md", "project": "项目A", "type": "文档", "date": "20260601"}]
        plan = batch_rename_plan(files)
        assert len(plan) == 1
        assert plan[0]["new_name"] == "项目A-文档-20260601-001.md"
        assert plan[0]["original"] == "test.md"
        assert plan[0]["id"] == "1"

    def test_seq_increment_same_group(self):
        files = [
            {"id": "1", "filename": "a.pdf", "project": "项目A", "type": "文档", "date": "20260601"},
            {"id": "2", "filename": "b.pdf", "project": "项目A", "type": "文档", "date": "20260601"},
            {"id": "3", "filename": "c.pdf", "project": "项目A", "type": "文档", "date": "20260601"},
        ]
        plan = batch_rename_plan(files)
        names = [p["new_name"] for p in plan]
        assert names[0].endswith("-001.pdf")
        assert names[1].endswith("-002.pdf")
        assert names[2].endswith("-003.pdf")

    def test_different_groups_reset_seq(self):
        files = [
            {"id": "1", "filename": "a.pdf", "project": "项目A", "type": "文档", "date": "20260601"},
            {"id": "2", "filename": "b.pdf", "project": "项目B", "type": "文档", "date": "20260601"},
        ]
        plan = batch_rename_plan(files)
        assert plan[0]["new_name"].endswith("-001.pdf")
        assert plan[1]["new_name"].endswith("-001.pdf")

    def test_default_project(self):
        files = [{"id": "1", "filename": "test.txt", "project": "", "type": "", "date": ""}]
        plan = batch_rename_plan(files, project_default="默认项目")
        assert "默认项目" in plan[0]["new_name"]

    def test_fallback_project(self):
        files = [{"id": "1", "filename": "test.txt", "project": "", "type": "", "date": ""}]
        plan = batch_rename_plan(files)
        assert "未分类" in plan[0]["new_name"]

    def test_preserves_ext(self):
        files = [{"id": "1", "filename": "report.pptx", "project": "ProjectX", "type": "汇报", "date": "20260101"}]
        plan = batch_rename_plan(files)
        assert plan[0]["new_name"].endswith(".pptx")


class TestDetectNamingConflicts:
    def test_no_conflicts(self):
        plan = [
            {"id": "1", "new_name": "项目A-文档-20260601-001.md"},
            {"id": "2", "new_name": "项目A-文档-20260601-002.md"},
        ]
        conflicts = detect_naming_conflicts(plan)
        assert conflicts == []

    def test_with_conflict(self):
        plan = [
            {"id": "1", "new_name": "same-name.md"},
            {"id": "2", "new_name": "different.md"},
            {"id": "3", "new_name": "same-name.md"},
        ]
        conflicts = detect_naming_conflicts(plan)
        assert len(conflicts) == 1
        assert conflicts[0]["name"] == "same-name.md"
        assert "1" in conflicts[0]["items"]
        assert "3" in conflicts[0]["items"]

    def test_multiple_conflicts(self):
        plan = [
            {"id": "1", "new_name": "dup.md"},
            {"id": "2", "new_name": "dup.md"},
            {"id": "3", "new_name": "dup2.pdf"},
            {"id": "4", "new_name": "dup2.pdf"},
        ]
        conflicts = detect_naming_conflicts(plan)
        assert len(conflicts) == 2


class TestSanitize:
    def test_illegal_chars(self):
        result = _sanitize('file:name/with\\illegal*chars?"<>|')
        assert ":" not in result
        assert "/" not in result
        assert "\\" not in result
        assert "*" not in result
        assert "?" not in result
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    def test_spaces_to_underscore(self):
        result = _sanitize("file name with spaces")
        assert " " not in result
        assert "_" in result

    def test_truncate_long(self):
        long_text = "a" * 100
        result = _sanitize(long_text)
        assert len(result) <= 30

    def test_empty_fallback(self):
        result = _sanitize("")
        assert result == "未命名"

    def test_whitespace_only(self):
        result = _sanitize("   ")
        assert result == "未命名"
