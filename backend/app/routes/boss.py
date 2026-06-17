# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.mock_data import MOCK_BOSS_DASHBOARD
from app.services import knowledge_stats

router = APIRouter(prefix="/api/boss", tags=["boss"])


@router.get("/dashboard")
def boss_dashboard(db: Session = Depends(get_db)):
    project_count = db.scalar(select(func.count(models.Project.id))) or 0
    active_projects = db.scalar(select(func.count(models.Project.id)).where(models.Project.status == "active")) or 0
    completed_projects = db.scalar(select(func.count(models.Project.id)).where(models.Project.status == "completed")) or 0

    task_total = db.scalar(select(func.count(models.ProjectTask.id))) or 0
    task_todo = db.scalar(select(func.count(models.ProjectTask.id)).where(models.ProjectTask.status == "todo")) or 0
    task_in_progress = db.scalar(select(func.count(models.ProjectTask.id)).where(models.ProjectTask.status.in_(["doing", "in_progress"]))) or 0
    task_done = db.scalar(select(func.count(models.ProjectTask.id)).where(models.ProjectTask.status.in_(["done", "completed"]))) or 0

    meeting_total = db.scalar(select(func.count(models.Meeting.id))) or 0
    meeting_scheduled = db.scalar(select(func.count(models.Meeting.id)).where(models.Meeting.status == "scheduled")) or 0
    meeting_completed = db.scalar(select(func.count(models.Meeting.id)).where(models.Meeting.status == "completed")) or 0

    recent_projects = list(db.scalars(select(models.Project).order_by(models.Project.updated_at.desc()).limit(5)))
    projects = list(db.scalars(select(models.Project).order_by(models.Project.updated_at.desc())))
    project_tasks = list(db.scalars(select(models.ProjectTask).order_by(models.ProjectTask.updated_at.desc()).limit(12)))
    recent_meetings = list(db.scalars(select(models.Meeting).order_by(models.Meeting.created_at.desc()).limit(8)))
    recent_cards = list(db.scalars(select(models.SkillCard).order_by(models.SkillCard.created_at.desc()).limit(12)))
    members = list(db.scalars(select(models.TeamMember).order_by(models.TeamMember.workload.desc()).limit(8)))
    employees = list(db.scalars(select(models.DigitalEmployee).order_by(models.DigitalEmployee.workload.desc()).limit(8)))
    recent_activities = [
        {"type": "project", "title": p.name, "time": str(p.updated_at)}
        for p in recent_projects
    ]
    phase_counts: dict[str, int] = {}
    for project in projects:
        phase_counts[project.phase or "未设置"] = phase_counts.get(project.phase or "未设置", 0) + 1
    card_type_counts: dict[str, int] = {}
    for card_type, count in db.execute(select(models.SkillCard.card_type, func.count(models.SkillCard.id)).group_by(models.SkillCard.card_type)):
        card_type_counts[card_type or "unknown"] = count

    return {
        "mode": "mock" if settings.mock_mode else "deepseek",
        **(MOCK_BOSS_DASHBOARD if settings.mock_mode else {}),
        "project_summary": {"total": project_count, "active": active_projects, "completed": completed_projects},
        "task_summary": {"total": task_total, "todo": task_todo, "in_progress": task_in_progress, "done": task_done},
        "meeting_summary": {"total": meeting_total, "scheduled": meeting_scheduled, "completed": meeting_completed},
        "recent_activities": recent_activities,
        "knowledge": knowledge_stats(db),
        "risk_alerts": [],
        "project_count": project_count,
        "active_project_count": active_projects,
        "task_count": db.scalar(select(func.count(models.ProjectTask.id))) or task_total,
        "open_task_count": len([task for task in project_tasks if task.status not in {"done", "completed"}]),
        "meeting_count": meeting_total,
        "skill_card_count": db.scalar(select(func.count(models.SkillCard.id))) or 0,
        "phase_counts": phase_counts,
        "risk_tasks": [
            {
                "id": task.id,
                "project_id": task.project_id,
                "task_name": task.task_name,
                "owner_role": task.owner_role,
                "risk_level": task.risk_level,
                "status": task.status,
            }
            for task in project_tasks
            if task.risk_level in {"高", "high", "中"} or task.status not in {"done", "completed"}
        ],
        "recent_meetings": [
            {
                "id": meeting.id,
                "project_id": meeting.project_id,
                "title": meeting.title,
                "status": meeting.status,
                "scheduled_at": meeting.scheduled_at,
                "next_actions": [],
            }
            for meeting in recent_meetings
        ],
        "recent_skill_cards": [
            {
                "id": card.id,
                "project_id": card.project_id,
                "card_type": card.card_type,
                "title": card.title,
                "status": card.status,
                "source": card.source,
            }
            for card in recent_cards
        ],
        "member_load": [
            {"id": item.id, "name": item.name, "role": item.role, "workload": item.workload, "type": "human"}
            for item in members
        ]
        + [
            {"id": item.id, "name": item.name, "role": item.role, "workload": item.workload, "type": "ai"}
            for item in employees
        ],
        "ai_card_distribution": card_type_counts,
    }
