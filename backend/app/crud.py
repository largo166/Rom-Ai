from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas


def list_projects(db: Session) -> list[models.Project]:
    return list(db.scalars(select(models.Project).order_by(models.Project.updated_at.desc())))


def get_project(db: Session, project_id: str) -> Optional[models.Project]:
    return db.scalar(
        select(models.Project)
        .where(models.Project.id == project_id)
        .options(
            selectinload(models.Project.files),
            selectinload(models.Project.reports),
            selectinload(models.Project.tasks),
            selectinload(models.Project.timelines),
            selectinload(models.Project.team_plans),
            selectinload(models.Project.knowledge_references),
            selectinload(models.Project.agent_runs),
            selectinload(models.Project.agent_triggers),
            selectinload(models.Project.meetings),
            selectinload(models.Project.skill_cards),
            selectinload(models.Project.team_assignments),
        )
    )


def create_project(db: Session, payload: schemas.ProjectCreate) -> models.Project:
    project = models.Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project
