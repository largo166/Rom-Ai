# -*- coding: utf-8 -*-
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.config import settings
from app.database import get_db
from app.json_safety import safe_json_parse, safe_json_dump
from app.mock_data import MOCK_TASK_BREAKDOWN, MOCK_PPT_STRUCTURE, MOCK_TECH_POINTS, MOCK_MEETING_MINUTES
from app.services import call_deepseek_text
from app.utils import utc_now

router = APIRouter(prefix="/api/projects/{project_id}/skill-cards", tags=["skill-cards"])

MOCK_OUTPUT_MAP = {
    "task_breakdown": MOCK_TASK_BREAKDOWN,
    "tech_points": MOCK_TECH_POINTS,
    "meeting_minutes": MOCK_MEETING_MINUTES,
    "ppt_structure": MOCK_PPT_STRUCTURE,
}


def _get_project_or_404(db: Session, project_id: str) -> models.Project:
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("", response_model=list[schemas.SkillCardOut])
def list_skill_cards(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    return list(db.scalars(
        select(models.SkillCard)
        .where(models.SkillCard.project_id == project_id)
        .order_by(models.SkillCard.created_at.desc())
    ))


@router.post("", response_model=schemas.SkillCardOut, status_code=201)
def create_skill_card(project_id: str, payload: schemas.SkillCardCreate, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    card = models.SkillCard(project_id=project_id, **payload.model_dump())
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.get("/{card_id}", response_model=schemas.SkillCardOut)
def get_skill_card(project_id: str, card_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    card = db.scalar(select(models.SkillCard).where(models.SkillCard.id == card_id))
    if not card:
        raise HTTPException(status_code=404, detail="技能卡片不存在")
    return card


@router.post("/{card_id}/execute")
async def execute_skill_card(project_id: str, card_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    card = db.scalar(select(models.SkillCard).where(models.SkillCard.id == card_id))
    if not card:
        raise HTTPException(status_code=404, detail="技能卡片不存在")

    card.status = "running"
    db.commit()

    mock_output = MOCK_OUTPUT_MAP.get(card.card_type, {"result": "mock output"})

    if settings.mock_mode:
        output = mock_output
    else:
        card_type_prompts = {
            "task_breakdown": "请基于项目信息生成任务拆解列表，输出 JSON 数组，每项包含 title、priority、assignee_type、due_days。",
            "tech_points": "请生成建筑设计技术重点卡片，输出 JSON 数组，每项包含 dimension、level、content、risk。",
            "meeting_minutes": "请生成会议纪要，输出 JSON，包含 summary、key_decisions、todos、next_meeting。",
            "ppt_structure": "请生成 PPT 结构大纲，输出 JSON，包含 title、sections 数组（每项含 page、title、content）。",
        }
        prompt = (
            f"{card_type_prompts.get(card.card_type, '请基于项目信息生成分析结果，输出 JSON。')}\n\n"
            f"项目：{project.name}\n"
            f"城市：{project.city}\n"
            f"类型：{project.project_type}\n"
            f"阶段：{project.phase}\n"
            f"输入数据：{card.input_data}\n"
        )
        try:
            raw = await call_deepseek_text(
                prompt=prompt,
                system_prompt="你是建筑设计项目分析助手。只输出 JSON，不要输出 Markdown。",
            )
            import re
            match = re.search(r"\{.*\}|\[.*\]", raw, re.S)
            output = safe_json_parse(match.group(0), default=mock_output, field_name="skill_card_output") if match else mock_output
        except Exception:
            output = mock_output

    card.output_data = safe_json_dump(output, field_name="skill_card_output_data")
    card.status = "completed"
    card.completed_at = utc_now()
    db.commit()
    db.refresh(card)
    return {"card_id": card.id, "output": output, "status": "completed"}
