"""AI agent catalog routes.

Boundary:
- /api/agents exposes the AI capability catalog and legacy agent-run entry.
- /api/projects/{project_id}/agent-chat in projects.py is the authoritative
  runtime entry for creating new skill result cards from user intent.
- /api/projects/{project_id}/skill-cards is the result-card compatibility API.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.cloud import mirror_agent_run
from app.database import get_db
from app.json_safety import safe_json_dump

router = APIRouter(prefix="/api/agents", tags=["agents"])

AGENTS = [
    {
        "id": "project-parser",
        "name": "项目解析代理",
        "scenario": "读取项目报告、任务和知识库引用，生成下一步执行建议。",
        "input": "ProjectReport / ProjectTask / KnowledgeReference",
        "output": "任务执行建议、汇报框架、PPT目录、图像提示词、人工确认问题",
        "status": "available",
    },
    {"id": "masterplan", "name": "总图分析代理", "scenario": "强排与总图判断", "input": "项目资料", "output": "总图策略", "status": "developing"},
    {"id": "unit", "name": "户型策略代理", "scenario": "产品与户型推演", "input": "产品定位", "output": "户型策略", "status": "developing"},
    {"id": "facade", "name": "立面风格代理", "scenario": "立面与材料研究", "input": "风格目标", "output": "立面策略", "status": "developing"},
    {"id": "landscape", "name": "景观策略代理", "scenario": "景观节点与动线", "input": "景观资料", "output": "景观策略", "status": "developing"},
    {"id": "interior", "name": "室内策略代理", "scenario": "大堂会所与精装", "input": "室内需求", "output": "室内策略", "status": "developing"},
    {"id": "ppt", "name": "PPT生成代理", "scenario": "汇报成果组织", "input": "报告与图像", "output": "PPT目录", "status": "developing"},
]


@router.get("")
def list_agents():
    return {"agents": AGENTS}


@router.post("/{agent_id}/run", response_model=schemas.AgentRunOut)
def run_agent(agent_id: str, payload: schemas.AgentRunRequest, db: Session = Depends(get_db)):
    agent = next((item for item in AGENTS if item["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    if agent["status"] != "available":
        raise HTTPException(status_code=400, detail="该代理仍在开发中")
    project = crud.get_project(db, payload.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    latest_report = project.reports[-1] if project.reports else None
    tasks = project.tasks[:8]
    refs = project.knowledge_references[:8]
    output = {
        "mode": "mock",
        "agent_name": agent["name"],
        "execution_advice": [
            "先核对项目资料和缺失清单。",
            "把高风险任务交给对应数字员工形成子任务。",
            "将知识库引用转化为汇报依据。",
        ],
        "presentation_framework": ["项目背景", "核心判断", "设计难点", "任务计划", "风险与下一步"],
        "ppt_outline": ["封面", "项目概况", "资料完整度", "关键难点", "任务拆解", "团队配置", "下一步计划"],
        "image_prompts": [
            f"{project.name} 建筑方案汇报主视觉，强调项目阶段 {project.phase} 的设计重点，建筑体量清晰，材料真实。",
        ],
        "human_questions": ["当前甲方最关注成本、速度还是形象？", "是否已有明确展示区范围？"],
        "source_counts": {"reports": 1 if latest_report else 0, "tasks": len(tasks), "knowledge_references": len(refs)},
    }
    run = models.AgentRun(
        project_id=project.id,
        agent_id=agent_id,
        input_context=safe_json_dump({"goal": payload.goal}, field_name="agent_input_context"),
        output_json=safe_json_dump(output, field_name="agent_output_json"),
        status="succeeded",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    mirror_agent_run(project.id, run.id, run.agent_id, run.input_context, run.output_json, run.status)
    return run
