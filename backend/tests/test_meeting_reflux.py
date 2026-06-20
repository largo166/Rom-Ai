"""test_meeting_reflux.py — 测试会议纪要自动回流机制"""
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Meeting, Project, ProjectTask, SkillCard
from app.services.meeting_reflux import (
    check_okf_staleness,
    execute_meeting_reflux,
    reflux_demand_translation,
    reflux_risks,
    reflux_tasks,
)


class MeetingRefluxTestBase(unittest.TestCase):
    """公共 setUp：内存 SQLite + 基础数据"""

    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def _create_project(self, db, **kwargs):
        project = Project(name="测试项目", city="杭州", **kwargs)
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    def _create_meeting(self, db, project):
        meeting = Meeting(project_id=project.id, title="需求对接会")
        db.add(meeting)
        db.commit()
        db.refresh(meeting)
        return meeting


# ─────────────────────────────────────────────────────────────────────
# reflux_demand_translation
# ─────────────────────────────────────────────────────────────────────

class TestRefluxDemandTranslation(MeetingRefluxTestBase):
    """甲方诉求回流测试"""

    def test_adds_new_demands_to_empty_project(self):
        """空项目：新增诉求正确写入 client_demands"""
        db = self.open_temp_db()
        project = self._create_project(db)

        demands = [
            {
                "raw": "要有大入口",
                "translation": "需要宏观轴线感",
                "confidence": "high",
                "category": "形象",
            }
        ]
        new = reflux_demand_translation(db, project, demands)

        assert len(new) == 1
        assert new[0]["raw"] == "要有大入口"
        assert new[0]["source"] == "meeting"

        import json
        stored = json.loads(project.client_demands)
        assert len(stored) == 1
        assert stored[0]["raw"] == "要有大入口"

    def test_dedup_same_raw_text(self):
        """相同 raw 文本不重复写入"""
        db = self.open_temp_db()
        project = self._create_project(db)

        demands = [{"raw": "要有大入口", "translation": "轴线感"}]
        reflux_demand_translation(db, project, demands)

        # 再次传入相同 raw
        new = reflux_demand_translation(db, project, demands)
        assert len(new) == 0

        import json
        stored = json.loads(project.client_demands)
        assert len(stored) == 1  # 仍然只有 1 条

    def test_merges_with_existing_demands(self):
        """与已有 client_demands 合并，不丢失旧数据"""
        import json
        db = self.open_temp_db()
        project = self._create_project(db)
        project.client_demands = json.dumps([{"raw": "旧诉求", "translation": "旧翻译", "source": "manual"}])
        db.commit()

        new = reflux_demand_translation(db, project, [{"raw": "新诉求", "translation": "新翻译"}])
        assert len(new) == 1

        stored = json.loads(project.client_demands)
        assert len(stored) == 2
        raws = [d["raw"] for d in stored]
        assert "旧诉求" in raws
        assert "新诉求" in raws

    def test_skips_empty_raw(self):
        """raw 为空字符串的条目被跳过"""
        db = self.open_temp_db()
        project = self._create_project(db)

        new = reflux_demand_translation(db, project, [{"raw": "", "translation": "没有原文"}])
        assert len(new) == 0
        assert project.client_demands is None or project.client_demands == ""

    def test_skips_non_dict_items(self):
        """非 dict 条目被跳过，不引发异常"""
        db = self.open_temp_db()
        project = self._create_project(db)

        new = reflux_demand_translation(db, project, ["字符串条目", None, 123])
        assert len(new) == 0

    def test_multiple_demands_at_once(self):
        """一次性传入多条诉求均被写入"""
        db = self.open_temp_db()
        project = self._create_project(db)

        demands = [
            {"raw": "诉求A", "translation": "翻译A"},
            {"raw": "诉求B", "translation": "翻译B"},
            {"raw": "诉求C", "translation": "翻译C"},
        ]
        new = reflux_demand_translation(db, project, demands)
        assert len(new) == 3

        import json
        stored = json.loads(project.client_demands)
        assert len(stored) == 3


# ─────────────────────────────────────────────────────────────────────
# reflux_risks
# ─────────────────────────────────────────────────────────────────────

class TestRefluxRisks(MeetingRefluxTestBase):
    """风险回流测试"""

    def test_adds_new_risks(self):
        """空项目：新增风险正确写入 risk_summary"""
        db = self.open_temp_db()
        project = self._create_project(db)

        new = reflux_risks(db, project, ["地质条件复杂", "报批周期长"])
        assert len(new) == 2

        import json
        stored = json.loads(project.risk_summary)
        assert "地质条件复杂" in stored
        assert "报批周期长" in stored

    def test_dedup_exact_text(self):
        """完全相同的风险文本不重复写入"""
        db = self.open_temp_db()
        project = self._create_project(db)

        reflux_risks(db, project, ["地质条件复杂"])
        new = reflux_risks(db, project, ["地质条件复杂"])

        assert len(new) == 0
        import json
        stored = json.loads(project.risk_summary)
        assert len(stored) == 1

    def test_merges_with_existing_risks(self):
        """与已有 risk_summary 合并，不丢失旧数据"""
        import json
        db = self.open_temp_db()
        project = self._create_project(db)
        project.risk_summary = json.dumps(["旧风险"])
        db.commit()

        new = reflux_risks(db, project, ["新风险"])
        assert len(new) == 1

        stored = json.loads(project.risk_summary)
        assert len(stored) == 2
        assert "旧风险" in stored
        assert "新风险" in stored

    def test_skips_empty_strings(self):
        """空字符串风险被跳过"""
        db = self.open_temp_db()
        project = self._create_project(db)

        new = reflux_risks(db, project, ["", "   "])
        assert len(new) == 0

    def test_accepts_non_string_risk_items(self):
        """非字符串风险被 str() 转换后写入"""
        db = self.open_temp_db()
        project = self._create_project(db)

        new = reflux_risks(db, project, [42, {"complex": "risk"}])
        assert len(new) == 2


# ─────────────────────────────────────────────────────────────────────
# reflux_tasks
# ─────────────────────────────────────────────────────────────────────

class TestRefluxTasks(MeetingRefluxTestBase):
    """任务回流测试"""

    def test_creates_new_tasks(self):
        """待办被创建为 ProjectTask，source_type=meeting"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        todos = [
            {"title": "完成景观方案", "priority": "high", "owner": "景观设计师"},
        ]
        created = reflux_tasks(db, project, meeting, todos)
        assert len(created) == 1

        task = db.query(ProjectTask).filter_by(project_id=project.id).first()
        assert task is not None
        assert task.task_name == "完成景观方案"
        assert task.priority == "high"
        assert task.owner_role == "景观设计师"
        assert task.source_type == "meeting"
        assert task.source_id == meeting.id
        assert task.task_type == "meeting_action"

    def test_does_not_duplicate_existing_task(self):
        """已存在同名任务时不重复创建"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        # 预先创建同名任务
        existing = ProjectTask(project_id=project.id, task_name="完成景观方案")
        db.add(existing)
        db.commit()

        created = reflux_tasks(db, project, meeting, [{"title": "完成景观方案"}])
        assert len(created) == 0

        count = db.query(ProjectTask).filter_by(project_id=project.id).count()
        assert count == 1

    def test_supports_task_name_key(self):
        """支持 task_name 键作为标题"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        created = reflux_tasks(db, project, meeting, [{"task_name": "提交规划报批材料"}])
        assert len(created) == 1
        assert created[0].task_name == "提交规划报批材料"

    def test_supports_task_key(self):
        """支持 task 键作为标题（action_items 格式）"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        created = reflux_tasks(db, project, meeting, [{"task": "协调甲方签字"}])
        assert len(created) == 1
        assert created[0].task_name == "协调甲方签字"

    def test_skips_empty_title(self):
        """标题为空的条目被跳过"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        created = reflux_tasks(db, project, meeting, [{"title": ""}, {}])
        assert len(created) == 0

    def test_skips_non_dict_todos(self):
        """非 dict 条目被跳过"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        created = reflux_tasks(db, project, meeting, ["字符串任务", None])
        assert len(created) == 0

    def test_creates_multiple_tasks(self):
        """一次创建多个任务"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        todos = [
            {"title": "任务A"},
            {"title": "任务B"},
            {"title": "任务C"},
        ]
        created = reflux_tasks(db, project, meeting, todos)
        assert len(created) == 3

        count = db.query(ProjectTask).filter_by(project_id=project.id).count()
        assert count == 3


# ─────────────────────────────────────────────────────────────────────
# check_okf_staleness
# ─────────────────────────────────────────────────────────────────────

class TestCheckOkfStaleness(MeetingRefluxTestBase):
    """OKF 过期检测测试"""

    def _create_skill_card(self, db, project, card_type):
        card = SkillCard(project_id=project.id, card_type=card_type, title=f"{card_type}卡")
        db.add(card)
        db.commit()
        return card

    def test_no_skill_cards_returns_empty(self):
        """项目无 SkillCard 时返回空列表"""
        db = self.open_temp_db()
        project = self._create_project(db)

        stale = check_okf_staleness(db, project, {"demand_translation": [{"raw": "诉求"}], "risks": ["风险"]})
        assert stale == []

    def test_detects_technical_focus_stale(self):
        """有新甲方诉求 + technical_focus 卡 → 该卡被标记为过期"""
        db = self.open_temp_db()
        project = self._create_project(db)
        self._create_skill_card(db, project, "technical_focus")

        stale = check_okf_staleness(db, project, {"demand_translation": [{"raw": "要有亮点"}], "risks": []})
        assert "technical_focus" in stale

    def test_detects_task_breakdown_stale_on_risk(self):
        """有新风险 + task_breakdown 卡 → 该卡被标记为过期"""
        db = self.open_temp_db()
        project = self._create_project(db)
        self._create_skill_card(db, project, "task_breakdown")

        stale = check_okf_staleness(db, project, {"demand_translation": [], "risks": ["地质风险"]})
        assert "task_breakdown" in stale

    def test_detects_task_breakdown_stale_on_schedule_category(self):
        """诉求 category 为"进度" + task_breakdown 卡 → 该卡被标记为过期"""
        db = self.open_temp_db()
        project = self._create_project(db)
        self._create_skill_card(db, project, "task_breakdown")

        stale = check_okf_staleness(
            db,
            project,
            {"demand_translation": [{"raw": "加快进度", "category": "进度"}], "risks": []},
        )
        assert "task_breakdown" in stale

    def test_no_stale_when_unrelated_card_type(self):
        """SkillCard 类型与规则不匹配时不触发过期"""
        db = self.open_temp_db()
        project = self._create_project(db)
        self._create_skill_card(db, project, "other_type")

        stale = check_okf_staleness(
            db,
            project,
            {"demand_translation": [{"raw": "诉求"}], "risks": ["风险"]},
        )
        assert stale == []

    def test_no_stale_when_empty_content(self):
        """空的 demand_translation 和 risks 不触发过期"""
        db = self.open_temp_db()
        project = self._create_project(db)
        self._create_skill_card(db, project, "technical_focus")
        self._create_skill_card(db, project, "task_breakdown")

        stale = check_okf_staleness(db, project, {"demand_translation": [], "risks": []})
        assert stale == []


# ─────────────────────────────────────────────────────────────────────
# execute_meeting_reflux（完整流程）
# ─────────────────────────────────────────────────────────────────────

class TestExecuteMeetingReflux(MeetingRefluxTestBase):
    """execute_meeting_reflux 完整流程测试"""

    def test_full_reflux_returns_summary(self):
        """完整流程返回正确的回流摘要"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        minutes = {
            "demand_translation": [
                {"raw": "要有大入口", "translation": "轴线感", "category": "形象"},
            ],
            "risks": ["地质条件复杂"],
            "todos": [{"title": "完成景观方案", "priority": "high"}],
        }

        summary = execute_meeting_reflux(db, project, meeting, minutes)

        assert summary["demands_added"] == 1
        assert summary["risks_added"] == 1
        assert summary["tasks_created"] == 1
        assert isinstance(summary["okf_stale_cards"], list)

    def test_full_reflux_with_empty_content(self):
        """空内容回流不报错，返回全零摘要"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        summary = execute_meeting_reflux(db, project, meeting, {})

        assert summary["demands_added"] == 0
        assert summary["risks_added"] == 0
        assert summary["tasks_created"] == 0
        assert summary["okf_stale_cards"] == []

    def test_full_reflux_idempotent_on_second_run(self):
        """同样内容执行两次，第二次不会重复写入"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        minutes = {
            "demand_translation": [{"raw": "要有大入口", "translation": "轴线感"}],
            "risks": ["地质条件复杂"],
            "todos": [{"title": "完成景观方案"}],
        }

        execute_meeting_reflux(db, project, meeting, minutes)
        # 需要 refresh project 以获取最新状态
        db.refresh(project)

        summary2 = execute_meeting_reflux(db, project, meeting, minutes)

        assert summary2["demands_added"] == 0
        assert summary2["risks_added"] == 0
        assert summary2["tasks_created"] == 0

    def test_full_reflux_emits_change_events(self):
        """有新诉求和风险时触发对应变更事件"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        from app.models import ProjectChangeEvent

        minutes = {
            "demand_translation": [{"raw": "要有大入口"}],
            "risks": ["地质条件复杂"],
            "todos": [],
        }

        execute_meeting_reflux(db, project, meeting, minutes)

        events = db.query(ProjectChangeEvent).filter_by(project_id=project.id).all()
        event_types = {e.event_type for e in events}
        assert "client_demands_updated" in event_types
        assert "risk_updated" in event_types

    def test_full_reflux_supports_action_items_key(self):
        """兼容 action_items 字段名（confirm-minutes 请求体格式）"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        minutes = {
            "demand_translation": [],
            "risks": [],
            "action_items": [{"title": "通过 action_items 创建的任务"}],
        }

        summary = execute_meeting_reflux(db, project, meeting, minutes)
        assert summary["tasks_created"] == 1

    def test_full_reflux_with_skill_cards_detects_stale(self):
        """有 SkillCard 且有新诉求/风险时检测到过期卡"""
        db = self.open_temp_db()
        project = self._create_project(db)
        meeting = self._create_meeting(db, project)

        # 创建 technical_focus 卡
        card = SkillCard(project_id=project.id, card_type="technical_focus", title="技术重心卡")
        db.add(card)
        db.commit()

        minutes = {
            "demand_translation": [{"raw": "要有亮点设计", "category": "形象"}],
            "risks": [],
            "todos": [],
        }

        summary = execute_meeting_reflux(db, project, meeting, minutes)
        assert "technical_focus" in summary["okf_stale_cards"]


if __name__ == "__main__":
    unittest.main()
