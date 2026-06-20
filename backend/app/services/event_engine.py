"""项目变更事件引擎 - 统一管理项目变更的感知与追踪"""
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.json_safety import safe_json_dump
from app.models import ProjectChangeEvent, ProjectReport
from app.utils import utc_now


def emit_change_event(
    db: Session,
    project_id: str,
    event_type: str,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    affected_fields: Optional[list[str]] = None,
    old_snapshot: Optional[dict] = None,
    new_snapshot: Optional[dict] = None,
    description: Optional[str] = None,
) -> ProjectChangeEvent:
    """写入一条变更事件"""
    event = ProjectChangeEvent(
        project_id=project_id,
        event_type=event_type,
        source_type=source_type,
        source_id=source_id,
        affected_fields=safe_json_dump(affected_fields, field_name="affected_fields") if affected_fields else None,
        old_snapshot=safe_json_dump(old_snapshot, field_name="old_snapshot") if old_snapshot else None,
        new_snapshot=safe_json_dump(new_snapshot, field_name="new_snapshot") if new_snapshot else None,
        description=description,
        consumed_by_analysis=False,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_unconsumed_events(db: Session, project_id: str) -> list[ProjectChangeEvent]:
    """获取尚未被增量分析消费的事件"""
    return (
        db.query(ProjectChangeEvent)
        .filter(
            ProjectChangeEvent.project_id == project_id,
            ProjectChangeEvent.consumed_by_analysis == False,  # noqa: E712
        )
        .order_by(ProjectChangeEvent.created_at.asc())
        .all()
    )


def mark_events_consumed(db: Session, event_ids: list) -> int:
    """标记事件已被分析消费"""
    if not event_ids:
        return 0
    now = utc_now()
    count = (
        db.query(ProjectChangeEvent)
        .filter(ProjectChangeEvent.id.in_(event_ids))
        .update(
            {"consumed_by_analysis": True, "consumed_at": now},
            synchronize_session="fetch",
        )
    )
    db.commit()
    return count


def get_project_change_timeline(
    db: Session,
    project_id: str,
    days: int = 30,
    event_type: Optional[str] = None,
) -> list[ProjectChangeEvent]:
    """查询项目近 N 天的变更时间线"""
    cutoff = utc_now() - timedelta(days=days)
    query = db.query(ProjectChangeEvent).filter(
        ProjectChangeEvent.project_id == project_id,
        ProjectChangeEvent.created_at >= cutoff,
    )
    if event_type:
        query = query.filter(ProjectChangeEvent.event_type == event_type)
    return query.order_by(ProjectChangeEvent.created_at.desc()).all()


def get_analysis_freshness(db: Session, project_id: str) -> dict:
    """检查项目分析是否过期"""
    # 最近一次分析
    last_report = (
        db.query(ProjectReport)
        .filter(
            ProjectReport.project_id == project_id,
            ProjectReport.report_type == "project_analysis",
        )
        .order_by(ProjectReport.created_at.desc())
        .first()
    )
    unconsumed = get_unconsumed_events(db, project_id)
    return {
        "is_stale": len(unconsumed) >= 3,
        "unconsumed_count": len(unconsumed),
        "last_analysis_date": last_report.created_at.isoformat() if last_report else None,
        "unconsumed_event_types": list(set(e.event_type for e in unconsumed)),
    }
