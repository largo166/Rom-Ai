"""
AI代理上下文与回写兼容端点

Runtime boundary:
- POST /api/projects/{project_id}/agent-chat is implemented in projects.py and
  calls services.execution.run_agent_chat.
- This module only exposes lightweight context and writeback compatibility.

GET  /api/projects/{project_id}/agent-context
POST /api/projects/{project_id}/agent-chat/writeback
"""
import logging
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db, serialized_write
from app.json_safety import safe_json_dump, safe_json_parse
from app.skill_manifest import list_builtin_skills

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def get_project_context(project_id: str, db: Session) -> dict:
    """读取项目上下文（绑定给Orchestrator用）"""
    from app.models import Meeting, Project, ProjectFile, ProjectReport, ProjectTask

    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        return {}

    files_count = db.query(ProjectFile).filter_by(project_id=project_id).count()
    meetings_count = db.query(Meeting).filter_by(project_id=project_id).count()
    tasks = db.query(ProjectTask).filter_by(project_id=project_id).all()
    latest_report = (
        db.query(ProjectReport)
        .filter_by(project_id=project_id)
        .order_by(ProjectReport.id.desc())
        .first()
    )

    return {
        "id": project.id,
        "name": project.name,
        "city": getattr(project, "city", "") or "",
        "project_type": getattr(project, "project_type", "") or "",
        "stage": getattr(project, "phase", "") or "",  # models.py 用 phase 字段
        "client_name": getattr(project, "client_name", "") or "",
        "files_count": files_count,
        "meetings_count": meetings_count,
        "tasks_total": len(tasks),
        "tasks_done": sum(1 for t in tasks if t.status == "done"),
        "latest_analysis": (
            safe_json_parse(latest_report.content_json, default={})
            if latest_report
            else {}
        ),
    }


def _extract_json_from_text(text: str) -> str:
    """从可能含Markdown包装的文本中提取JSON字符串"""
    if not text:
        return text
    # 去掉 ```json ... ``` 包装
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    # 尝试找到第一个 { ... } 块
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return text


# ─────────────────────────────────────────────
# 端点
# ─────────────────────────────────────────────

@router.get("/projects/{project_id}/agent-context")
async def get_agent_context(project_id: str, db: Session = Depends(get_db)):
    """获取当前项目的AI代理执行上下文（轻量版，给前端上下文条用）"""
    context = get_project_context(project_id, db)
    if not context:
        return JSONResponse({"error": "项目不存在"}, status_code=404)

    return {
        "project_name": context.get("name"),
        "stage": context.get("stage"),
        "city": context.get("city"),
        "project_type": context.get("project_type"),
        "files_read": context.get("files_count", 0),
        "meetings_read": context.get("meetings_count", 0),
        "knowledge_refs": 0,  # Phase 6
        "available_skills": [
            {
                "id": s["id"],
                "name": s["name"],
                "description": s["description"],
                "retrieval_required": s.get("retrieval_required", False),
            }
            for s in list_builtin_skills()
        ],
    }


@router.post("/projects/{project_id}/agent-chat/writeback")
async def writeback_result(
    project_id: str, request: Request, db: Session = Depends(get_db)
):
    """将成果卡回写到项目/任务/知识库"""
    from app.models import Project, ProjectReport, ProjectTask

    body = await request.json()
    card_type = body.get("card_type", "")
    result = body.get("result", {})
    target = body.get("target", "project_report")  # project_report / project_tasks

    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        return JSONResponse({"error": "项目不存在"}, status_code=404)

    written = 0
    with serialized_write():
        if target == "project_report":
            report = ProjectReport(
                project_id=project_id,
                report_type=card_type,
                content_json=safe_json_dump(result) or "{}",
            )
            db.add(report)
            written = 1

        elif target == "project_tasks" and isinstance(result, dict):
            tasks = result.get("tasks", [])
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                task = ProjectTask(
                    project_id=project_id,
                    task_name=str(t.get("title", ""))[:200],
                    output_requirement=str(t.get("description", "")),
                    priority=str(t.get("priority", "medium")),
                    estimated_days=int(t.get("estimated_days", 1)),
                    status="todo",
                )
                db.add(task)
                written += 1

        db.commit()

    return {"success": True, "target": target, "written": written}
