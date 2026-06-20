"""test_event_engine.py — 测试变更事件引擎的核心函数"""
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Project, ProjectChangeEvent, ProjectReport
from app.services.event_engine import (
    emit_change_event,
    get_unconsumed_events,
    mark_events_consumed,
    get_project_change_timeline,
    get_analysis_freshness,
)


class EventEngineTest(unittest.TestCase):
    """变更事件引擎核心逻辑测试"""

    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def _create_project(self, db):
        project = Project(name="测试项目", city="杭州")
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    # ── emit_change_event ──────────────────────────────────────

    def test_emit_change_event_normal_write(self):
        """emit_change_event 正常写入一条事件"""
        db = self.open_temp_db()
        project = self._create_project(db)

        event = emit_change_event(
            db, project.id, "file_uploaded",
            source_type="file", source_id="abc123",
            description="上传文件: 规划条件.pdf",
        )

        assert event.id is not None
        assert event.project_id == project.id
        assert event.event_type == "file_uploaded"
        assert event.source_type == "file"
        assert event.source_id == "abc123"
        assert event.description == "上传文件: 规划条件.pdf"
        assert event.consumed_by_analysis is False
        assert event.consumed_at is None

    def test_emit_change_event_with_affected_fields(self):
        """emit_change_event 携带 affected_fields 时正确序列化为 JSON"""
        db = self.open_temp_db()
        project = self._create_project(db)

        event = emit_change_event(
            db, project.id, "client_demands_updated",
            source_type="manual",
            affected_fields=["client_name", "client_demands"],
            description="更新甲方信息",
        )

        assert event.affected_fields is not None
        import json
        fields = json.loads(event.affected_fields)
        assert fields == ["client_name", "client_demands"]

    def test_emit_change_event_with_snapshots(self):
        """emit_change_event 携带 old_snapshot/new_snapshot 时正确序列化"""
        db = self.open_temp_db()
        project = self._create_project(db)

        event = emit_change_event(
            db, project.id, "client_demands_updated",
            source_type="manual",
            old_snapshot={"client_name": "旧甲方"},
            new_snapshot={"client_name": "新甲方"},
        )

        import json
        assert json.loads(event.old_snapshot) == {"client_name": "旧甲方"}
        assert json.loads(event.new_snapshot) == {"client_name": "新甲方"}

    def test_emit_change_event_none_optional_fields(self):
        """emit_change_event 可选字段为 None 时不写入"""
        db = self.open_temp_db()
        project = self._create_project(db)

        event = emit_change_event(
            db, project.id, "file_uploaded",
            description="简单事件",
        )

        assert event.source_type is None
        assert event.source_id is None
        assert event.affected_fields is None
        assert event.old_snapshot is None
        assert event.new_snapshot is None

    # ── get_unconsumed_events ──────────────────────────────────

    def test_get_unconsumed_events_filters_unconsumed(self):
        """get_unconsumed_events 只返回未消费的事件"""
        db = self.open_temp_db()
        project = self._create_project(db)

        emit_change_event(db, project.id, "file_uploaded", description="事件1")
        emit_change_event(db, project.id, "meeting_confirmed", description="事件2")
        emit_change_event(db, project.id, "file_uploaded", description="事件3")

        unconsumed = get_unconsumed_events(db, project.id)
        assert len(unconsumed) == 3

    def test_get_unconsumed_events_excludes_consumed(self):
        """get_unconsumed_events 排除已消费事件"""
        db = self.open_temp_db()
        project = self._create_project(db)

        e1 = emit_change_event(db, project.id, "file_uploaded", description="事件1")
        e2 = emit_change_event(db, project.id, "meeting_confirmed", description="事件2")

        # 手动标记 e1 为已消费
        mark_events_consumed(db, [e1.id])

        unconsumed = get_unconsumed_events(db, project.id)
        assert len(unconsumed) == 1
        assert unconsumed[0].id == e2.id

    def test_get_unconsumed_events_filters_by_project(self):
        """get_unconsumed_events 按项目 ID 过滤"""
        db = self.open_temp_db()
        p1 = self._create_project(db)
        p2 = Project(name="另一个项目", city="上海")
        db.add(p2)
        db.commit()
        db.refresh(p2)

        emit_change_event(db, p1.id, "file_uploaded", description="P1事件")
        emit_change_event(db, p2.id, "file_uploaded", description="P2事件")

        assert len(get_unconsumed_events(db, p1.id)) == 1
        assert len(get_unconsumed_events(db, p2.id)) == 1

    # ── mark_events_consumed ───────────────────────────────────

    def test_mark_events_consumed_batch(self):
        """mark_events_consumed 批量标记事件为已消费"""
        db = self.open_temp_db()
        project = self._create_project(db)

        e1 = emit_change_event(db, project.id, "file_uploaded", description="事件1")
        e2 = emit_change_event(db, project.id, "meeting_confirmed", description="事件2")
        e3 = emit_change_event(db, project.id, "file_uploaded", description="事件3")

        count = mark_events_consumed(db, [e1.id, e3.id])
        assert count == 2

        unconsumed = get_unconsumed_events(db, project.id)
        assert len(unconsumed) == 1
        assert unconsumed[0].id == e2.id

    def test_mark_events_consumed_empty_list(self):
        """mark_events_consumed 传入空列表时返回 0"""
        db = self.open_temp_db()
        count = mark_events_consumed(db, [])
        assert count == 0

    def test_mark_events_consumed_sets_consumed_at(self):
        """mark_events_consumed 设置 consumed_at 时间戳"""
        db = self.open_temp_db()
        project = self._create_project(db)

        event = emit_change_event(db, project.id, "file_uploaded", description="事件")
        assert event.consumed_at is None

        mark_events_consumed(db, [event.id])

        db.refresh(event)
        assert event.consumed_at is not None

    # ── get_analysis_freshness ─────────────────────────────────

    def test_get_analysis_freshness_stale_when_3_unconsumed(self):
        """>=3 条未消费事件时 is_stale 为 True"""
        db = self.open_temp_db()
        project = self._create_project(db)

        emit_change_event(db, project.id, "file_uploaded", description="事件1")
        emit_change_event(db, project.id, "file_uploaded", description="事件2")
        emit_change_event(db, project.id, "meeting_confirmed", description="事件3")

        freshness = get_analysis_freshness(db, project.id)
        assert freshness["is_stale"] is True
        assert freshness["unconsumed_count"] == 3

    def test_get_analysis_freshness_not_stale_under_3(self):
        """<3 条未消费事件时 is_stale 为 False"""
        db = self.open_temp_db()
        project = self._create_project(db)

        emit_change_event(db, project.id, "file_uploaded", description="事件1")
        emit_change_event(db, project.id, "meeting_confirmed", description="事件2")

        freshness = get_analysis_freshness(db, project.id)
        assert freshness["is_stale"] is False
        assert freshness["unconsumed_count"] == 2

    def test_get_analysis_freshness_no_events(self):
        """无事件时 is_stale 为 False，unconsumed_count 为 0"""
        db = self.open_temp_db()
        project = self._create_project(db)

        freshness = get_analysis_freshness(db, project.id)
        assert freshness["is_stale"] is False
        assert freshness["unconsumed_count"] == 0

    def test_get_analysis_freshness_with_last_report(self):
        """有分析报告时 last_analysis_date 不为 None"""
        db = self.open_temp_db()
        project = self._create_project(db)

        report = ProjectReport(
            project_id=project.id,
            report_type="project_analysis",
        )
        db.add(report)
        db.commit()

        freshness = get_analysis_freshness(db, project.id)
        assert freshness["last_analysis_date"] is not None

    def test_get_analysis_freshness_unconsumed_event_types(self):
        """unconsumed_event_types 返回去重后的事件类型"""
        db = self.open_temp_db()
        project = self._create_project(db)

        emit_change_event(db, project.id, "file_uploaded", description="事件1")
        emit_change_event(db, project.id, "file_uploaded", description="事件2")
        emit_change_event(db, project.id, "meeting_confirmed", description="事件3")

        freshness = get_analysis_freshness(db, project.id)
        assert set(freshness["unconsumed_event_types"]) == {"file_uploaded", "meeting_confirmed"}

    # ── get_project_change_timeline ────────────────────────────

    def test_get_project_change_timeline_returns_events(self):
        """get_project_change_timeline 返回项目变更时间线"""
        db = self.open_temp_db()
        project = self._create_project(db)

        emit_change_event(db, project.id, "file_uploaded", description="事件1")
        emit_change_event(db, project.id, "meeting_confirmed", description="事件2")

        timeline = get_project_change_timeline(db, project.id, days=30)
        assert len(timeline) == 2

    def test_get_project_change_timeline_filters_by_event_type(self):
        """get_project_change_timeline 按 event_type 过滤"""
        db = self.open_temp_db()
        project = self._create_project(db)

        emit_change_event(db, project.id, "file_uploaded", description="事件1")
        emit_change_event(db, project.id, "meeting_confirmed", description="事件2")

        timeline = get_project_change_timeline(db, project.id, days=30, event_type="file_uploaded")
        assert len(timeline) == 1
        assert timeline[0].event_type == "file_uploaded"
