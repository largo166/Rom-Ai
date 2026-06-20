# -*- coding: utf-8 -*-
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud, models
from app.config import settings
from app.database import get_db
from app.json_safety import safe_json_parse
from app.mock_data import MOCK_TECH_POINTS
from app.services import call_deepseek_text

router = APIRouter(prefix="/api/projects/{project_id}", tags=["tech-points"])


@router.post("/generate-tech-points")
async def generate_tech_points(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if settings.mock_mode:
        return {"mode": "mock", "project_id": project_id, "tech_points": MOCK_TECH_POINTS}

    prompt = (
        "请基于以下项目信息生成建筑设计技术重点卡片，输出 JSON 数组，"
        "每项包含 dimension（维度）、level（等级 high/medium/low）、content（内容描述）、risk（风险等级）。\n\n"
        f"项目：{project.name}\n"
        f"城市：{project.city}\n"
        f"类型：{project.project_type}\n"
        f"阶段：{project.phase}\n"
        f"描述：{project.description}\n"
    )
    try:
        raw = await call_deepseek_text(
            prompt=prompt,
            system_prompt="你是建筑设计技术分析助手。只输出 JSON 数组，不要输出 Markdown。",
        )
        import re
        match = re.search(r"\[.*\]", raw, re.S)
        tech_points = safe_json_parse(match.group(0), default=MOCK_TECH_POINTS, field_name="tech_points_json") if match else MOCK_TECH_POINTS
    except Exception:
        tech_points = MOCK_TECH_POINTS

    return {"mode": "deepseek", "project_id": project_id, "tech_points": tech_points}
