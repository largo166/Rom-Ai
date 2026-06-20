"""test_incremental_analysis.py — 测试增量分析的核心函数"""
import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    Meeting,
    Project,
    ProjectChangeEvent,
    ProjectFile,
    ProjectReport,
)
from app.services.analysis import (
    build_incremental_analysis_prompt,
    run_incremental_analysis,
    _mock_incremental_result,
    _format_incremental_diff,
)
from app.services.event_engine import (
    emit_change_event,
    get_unconsumed_events,
    mark_events_consumed,
)


class IncrementalAnalysisPromptTest(unittest.TestCase):
    """build_incremental_analysis_prompt 组装测试"""

    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_prompt_includes_project_name(self):
        project = Project(name="湖畔住宅", city="杭州", project_type="住宅", phase="方案")
        report = ProjectReport(markdown="# 上次分析\n项目为低密改善住宅", report_type="project_analysis")
        event = ProjectChangeEvent(
            project_id="fake", event_type="meeting_confirmed", description="确认会议纪要: 设计启动会"
        )

        prompt = build_incremental_analysis_prompt(project, report, [event])

        self.assertIn("湖畔住宅", prompt)
        self.assertIn("上次分析", prompt)
        self.assertIn("[meeting_confirmed]", prompt)
        self.assertIn("确认会议纪要", prompt)

    def test_prompt_includes_meeting_summary(self):
        project = Project(name="测试项目")
        report = ProjectReport(markdown="上次分析摘要", report_type="project_analysis")
        event = ProjectChangeEvent(project_id="fake", event_type="meeting_confirmed", description="会议纪要确认")
        meeting = Meeting(title="设计讨论会", summary="甲方要求增加立面品质")

        prompt = build_incremental_analysis_prompt(project, report, [event], recent_meetings=[meeting])

        self.assertIn("设计讨论会", prompt)
        self.assertIn("立面品质", prompt)

    def test_prompt_includes_file_content(self):
        project = Project(name="测试项目")
        report = ProjectReport(markdown="上次分析摘要", report_type="project_analysis")
        event = ProjectChangeEvent(project_id="fake", event_type="file_uploaded", description="上传新文件")
        file = ProjectFile(filename="规划条件.pdf", parsed_text="容积率2.5，限高60m")

        prompt = build_incremental_analysis_prompt(project, report, [event], new_files=[file])

        self.assertIn("规划条件.pdf", prompt)
        self.assertIn("容积率2.5", prompt)

    def test_prompt_with_no_events_shows_no_change(self):
        project = Project(name="测试项目")
        report = ProjectReport(markdown="上次分析摘要", report_type="project_analysis")

        prompt = build_incremental_analysis_prompt(project, report, [])

        self.assertIn("无新变更", prompt)

    def test_prompt_with_no_meetings_shows_no_meeting(self):
        project = Project(name="测试项目")
        report = ProjectReport(markdown="上次分析摘要", report_type="project_analysis")
        event = ProjectChangeEvent(project_id="fake", event_type="file_uploaded", description="新文件")

        prompt = build_incremental_analysis_prompt(project, report, [event], recent_meetings=None)

        self.assertIn("无新会议", prompt)

    def test_prompt_with_no_files_shows_no_file(self):
        project = Project(name="测试项目")
        report = ProjectReport(markdown="上次分析摘要", report_type="project_analysis")
        event = ProjectChangeEvent(project_id="fake", event_type="file_uploaded", description="新文件")

        prompt = build_incremental_analysis_prompt(project, report, [event], new_files=None)

        self.assertIn("无新文件", prompt)


class RunIncrementalAnalysisTest(unittest.TestCase):
    """run_incremental_analysis 端到端测试"""

    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def _create_project_with_report(self, db):
        """创建一个项目并附带一个 project_analysis 报告"""
        project = Project(name="测试项目", city="杭州", project_type="住宅", phase="方案")
        db.add(project)
        db.commit()
        db.refresh(project)

        report = ProjectReport(
            project_id=project.id,
            report_type="project_analysis",
            markdown="# 项目分析报告\n测试内容",
            content_json='{"mode": "mock"}',
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return project, report

    def test_no_previous_analysis_returns_no_previous(self):
        """无历史报告时返回 no_previous_analysis"""
        db = self.open_temp_db()
        project = Project(name="无报告项目")
        db.add(project)
        db.commit()
        db.refresh(project)

        result = asyncio.run(run_incremental_analysis(project.id, db))

        self.assertEqual(result["status"], "no_previous_analysis")
        self.assertIn("尚无历史分析报告", result["message"])
        db.close()

    def test_no_unconsumed_events_returns_no_change(self):
        """无未消费事件时返回 no_change_detected"""
        db = self.open_temp_db()
        project, report = self._create_project_with_report(db)

        result = asyncio.run(run_incremental_analysis(project.id, db))

        self.assertEqual(result["status"], "no_change_detected")
        self.assertIn("无新变更", result["message"])
        db.close()

    def test_incremental_analysis_with_events_completed(self):
        """有未消费事件时完成增量分析（mock settings.mock_mode=True）"""
        db = self.open_temp_db()
        project, report = self._create_project_with_report(db)

        # 创建未消费事件
        emit_change_event(db, project.id, "meeting_confirmed", description="确认会议纪要")
        emit_change_event(db, project.id, "file_uploaded", description="上传新规划条件")

        with patch('app.services.analysis.settings') as mock_settings:
            mock_settings.mock_mode = True
            mock_settings.deepseek_model = "mock"
            result = asyncio.run(run_incremental_analysis(project.id, db))

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["has_significant_change"])
        self.assertIn("立面品质", result["change_summary"])
        self.assertEqual(result["events_consumed"], 2)
        self.assertIn("report_id", result)
        self.assertIn("增量分析报告", result["diff_summary"])
        db.close()

    def test_events_marked_consumed_after_analysis(self):
        """增量分析后事件被标记为已消费"""
        db = self.open_temp_db()
        project, report = self._create_project_with_report(db)

        emit_change_event(db, project.id, "meeting_confirmed", description="会议纪要确认")
        emit_change_event(db, project.id, "file_uploaded", description="上传文件")

        # 分析前：有 2 个未消费事件
        before = get_unconsumed_events(db, project.id)
        self.assertEqual(len(before), 2)

        asyncio.run(run_incremental_analysis(project.id, db))

        # 分析后：所有事件被标记为已消费
        after = get_unconsumed_events(db, project.id)
        self.assertEqual(len(after), 0)
        db.close()

    def test_new_report_has_parent_report_id(self):
        """新报告的 parent_report_id 指向上次报告"""
        db = self.open_temp_db()
        project, report = self._create_project_with_report(db)

        emit_change_event(db, project.id, "meeting_confirmed", description="会议确认")

        result = asyncio.run(run_incremental_analysis(project.id, db))

        # 查找新报告
        new_report = db.query(ProjectReport).filter(
            ProjectReport.id == result["report_id"]
        ).first()
        self.assertIsNotNone(new_report)
        self.assertEqual(new_report.parent_report_id, report.id)
        self.assertEqual(new_report.report_type, "project_analysis")
        self.assertIsNotNone(new_report.diff_summary)
        db.close()

    def test_risk_summary_updated_from_delta_risks(self):
        """增量分析的 delta_risks 更新 project.risk_summary"""
        db = self.open_temp_db()
        project, report = self._create_project_with_report(db)

        emit_change_event(db, project.id, "meeting_confirmed", description="会议确认")

        # 初始 risk_summary 为 None
        self.assertIsNone(project.risk_summary)

        with patch('app.services.analysis.settings') as mock_settings:
            mock_settings.mock_mode = True
            mock_settings.deepseek_model = "mock"
            asyncio.run(run_incremental_analysis(project.id, db))

        db.refresh(project)
        # mock 结果包含 delta_risks add "立面造价可能超预算"
        from app.json_safety import safe_json_parse
        risks = safe_json_parse(project.risk_summary, default=[], field_name="risk_summary")
        self.assertIsInstance(risks, list)
        self.assertIn("立面造价可能超预算", risks)
        db.close()

    def test_project_not_found_raises_error(self):
        """项目不存在时抛出 ValueError"""
        db = self.open_temp_db()

        with self.assertRaises(ValueError):
            asyncio.run(run_incremental_analysis("nonexistent_id", db))
        db.close()


class MockIncrementalResultTest(unittest.TestCase):
    """_mock_incremental_result 结构完整性测试"""

    def test_mock_result_has_required_fields(self):
        result = _mock_incremental_result()

        self.assertIn("has_significant_change", result)
        self.assertIn("change_summary", result)
        self.assertIn("delta_technical_focus", result)
        self.assertIn("delta_tasks", result)
        self.assertIn("delta_risks", result)
        self.assertIn("resolved_questions", result)
        self.assertIn("okf_update_suggestions", result)

    def test_mock_result_delta_items_have_required_keys(self):
        result = _mock_incremental_result()

        for item in result["delta_technical_focus"]:
            self.assertIn("action", item)
            self.assertIn("item", item)
            self.assertIn("reason", item)

        for item in result["delta_tasks"]:
            self.assertIn("action", item)
            self.assertIn("task_name", item)
            self.assertIn("priority", item)
            self.assertIn("reason", item)

        for item in result["delta_risks"]:
            self.assertIn("action", item)
            self.assertIn("risk", item)
            self.assertIn("reason", item)

        for item in result["resolved_questions"]:
            self.assertIn("question", item)
            self.assertIn("answer", item)

    def test_mock_result_has_significant_change_is_true(self):
        result = _mock_incremental_result()
        self.assertTrue(result["has_significant_change"])


class FormatIncrementalDiffTest(unittest.TestCase):
    """_format_incremental_diff Markdown 格式化测试"""

    def test_format_complete_result(self):
        result = _mock_incremental_result()
        md = _format_incremental_diff(result)

        self.assertIn("# 增量分析报告", md)
        self.assertIn("**变更摘要**", md)
        self.assertIn("## 技术重点变化", md)
        self.assertIn("立面材料质感提升方案", md)
        self.assertIn("## 任务调整", md)
        self.assertIn("立面材料方案比选", md)
        self.assertIn("## 风险更新", md)
        self.assertIn("立面造价可能超预算", md)
        self.assertIn("## 已解答的开放问题", md)
        self.assertIn("甲方对立面风格的具体偏好", md)

    def test_format_empty_change_summary(self):
        result = {"change_summary": "", "delta_technical_focus": [], "delta_tasks": [], "delta_risks": [], "resolved_questions": []}
        md = _format_incremental_diff(result)

        self.assertIn("# 增量分析报告", md)
        # 没有各子标题因为列表为空
        self.assertNotIn("## 技术重点变化", md)

    def test_format_uses_emoji_for_actions(self):
        result = {
            "change_summary": "测试变更",
            "delta_technical_focus": [
                {"action": "add", "item": "新增技术点", "reason": "测试"},
                {"action": "modify", "item": "修改技术点", "reason": "测试"},
                {"action": "remove", "item": "删除技术点", "reason": "测试"},
            ],
            "delta_tasks": [
                {"action": "add", "task_name": "新任务", "priority": "high", "reason": "测试"},
                {"action": "reprioritize", "task_name": "调整任务", "priority": "medium", "reason": "测试"},
                {"action": "remove", "task_name": "删除任务", "priority": "low", "reason": "测试"},
            ],
            "delta_risks": [
                {"action": "add", "risk": "新增风险", "reason": "测试"},
                {"action": "resolve", "risk": "已解决风险", "reason": "测试"},
            ],
            "resolved_questions": [
                {"question": "开放问题", "answer": "解答"},
            ],
        }
        md = _format_incremental_diff(result)

        self.assertIn("➕", md)
        self.assertIn("✏️", md)
        self.assertIn("❌", md)
        self.assertIn("🔄", md)
        self.assertIn("⚠️", md)
        self.assertIn("✅", md)

    def test_format_resolved_questions_with_q_and_a(self):
        result = {
            "change_summary": "变更",
            "delta_technical_focus": [],
            "delta_tasks": [],
            "delta_risks": [],
            "resolved_questions": [
                {"question": "甲方具体要求是什么？", "answer": "石材+金属组合"},
            ],
        }
        md = _format_incremental_diff(result)

        self.assertIn("**Q**: 甲方具体要求是什么？", md)
        self.assertIn("**A**: 石材+金属组合", md)


if __name__ == "__main__":
    unittest.main()
