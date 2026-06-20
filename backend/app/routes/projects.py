from pathlib import Path
import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.cloud import mirror_agent_run, mirror_project_file, mirror_project_parse, mirror_project_report
from app.config import settings
from app.database import engine as db_engine, get_db
from app.json_safety import safe_json_dump, safe_json_parse


# ── Phase 3: 项目概览指挥台辅助函数 ─────────────────────────────────────────


def _serialise_task(task: models.ProjectTask) -> dict:
    return {
        "id": task.id,
        "task_name": task.task_name,
        "task_type": task.task_type,
        "priority": task.priority,
        "owner_role": task.owner_role,
        "estimated_days": task.estimated_days,
        "risk_level": task.risk_level,
        "status": task.status,
        "assignee_name": task.assignee_name or "",
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else "",
    }


def _serialise_meeting_brief(meeting: models.Meeting) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title or "",
        "date": meeting.date.isoformat() if meeting.date else None,
        "summary": (meeting.summary or meeting.agenda or "")[:500],
        "status": meeting.status,
        "created_at": meeting.created_at.isoformat() if meeting.created_at else "",
    }


def _aggregate_risks(project: models.Project) -> list[dict]:
    """从任务风险等级、risk_summary 字段、启动分析风险列表三个来源聚合风险项。"""
    risks: list[dict] = []
    seen_labels: set[str] = set()

    # 来源 1: 高风险任务
    for task in project.tasks:
        rl = (task.risk_level or "").lower()
        if rl in ("high", "高") or "高" in (task.risk_level or ""):
            label = task.task_name or task.id
            if label not in seen_labels:
                risks.append({
                    "source": "task",
                    "level": "high",
                    "title": task.task_name or "未命名任务",
                    "detail": task.output_requirement or "",
                    "ref_id": task.id,
                })
                seen_labels.add(label)

    # 来源 2: project.risk_summary (JSON)
    risk_summary = safe_json_parse(project.risk_summary, default=[], field_name="risk_summary")
    if isinstance(risk_summary, list):
        for item in risk_summary:
            if isinstance(item, dict):
                label = item.get("title") or item.get("name") or str(item)
                if label not in seen_labels:
                    risks.append({
                        "source": "summary",
                        "level": item.get("level", "medium"),
                        "title": label,
                        "detail": item.get("detail") or item.get("description") or "",
                        "ref_id": item.get("ref_id", ""),
                    })
                    seen_labels.add(label)

    # 来源 3: 最新启动分析报告中的 risk_list
    latest_report = None
    for report in sorted(project.reports, key=lambda r: r.created_at, reverse=True):
        latest_report = report
        break
    if latest_report:
        payload = safe_json_parse(latest_report.content_json or "{}", default={}, field_name="content_json")
        risk_list = payload.get("risk_list", []) if isinstance(payload, dict) else []
        if isinstance(risk_list, list):
            for item in risk_list:
                text = item if isinstance(item, str) else (item.get("title") or item.get("text") or str(item)) if isinstance(item, dict) else str(item)
                if text not in seen_labels:
                    risks.append({
                        "source": "analysis",
                        "level": "medium",
                        "title": text,
                        "detail": text,
                        "ref_id": latest_report.id,
                    })
                    seen_labels.add(text)

    return risks
from app.services import (
    SUPPORTED_PROJECT_EXTS,
    build_team_plan,
    call_deepseek_json,
    delete_project_library,
    ensure_project_sidecars,
    mock_analysis_payload,
    normalize_analysis_payload,
    parse_tencent_meeting_result,
    parse_document,
    project_okf_bundle_status,
    project_upload_dir,
    generate_project_okf_bundle,
    run_project_execution,
    run_agent_chat,
    run_skill_card,
    run_startup_analysis,
    save_analysis_result,
    scan_vault_directory,
    schedule_tencent_meeting,
    summarize_meeting,
    sync_tencent_meeting_minutes,
    team_requirements_from_payload,
    TencentMinutesUnavailableError,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

logger = logging.getLogger(__name__)


@router.get("", response_model=list[schemas.ProjectSummary])
def list_projects(db: Session = Depends(get_db)):
    projects = crud.list_projects(db)
    return [
        {
            **schemas.ProjectOut.model_validate(project).model_dump(),
            "file_count": len(project.files),
            "report_count": len(project.reports),
            "task_count": len(project.tasks),
        }
        for project in projects
    ]


@router.post("", response_model=schemas.ProjectOut)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    return crud.create_project(db, payload)


@router.get("/{project_id}", response_model=schemas.ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("/{project_id}/okf-bundle", response_model=schemas.OkfBundleOut)
def get_project_okf_bundle(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project_okf_bundle_status(project)


@router.post("/{project_id}/okf-bundle/generate", response_model=schemas.OkfBundleOut)
def generate_okf_bundle(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    try:
        return generate_project_okf_bundle(db, project)
    except Exception as exc:
        db.rollback()
        logger.exception("Data link bundle generation failed project=%s", project_id)
        raise HTTPException(status_code=500, detail=f"项目数据链接生成失败：{exc}")


# ── Phase 3: 项目概览指挥台端点 ─────────────────────────────────────────────


@router.get("/{project_id}/overview-dashboard")
def get_overview_dashboard(project_id: str, db: Session = Depends(get_db)):
    """聚合返回项目概览指挥台所需的全部数据。"""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_project_sidecars(db, project)
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # ── 指标 ──────────────────────────────────────────────────────────────
    tasks = project.tasks or []
    done_statuses = {"done", "completed", "已完成"}
    tasks_done = sum(1 for t in tasks if t.status in done_statuses)
    risks = _aggregate_risks(project)

    deliverables = safe_json_parse(project.deliverables, default=[], field_name="deliverables")
    if not isinstance(deliverables, list):
        deliverables = []
    deliverables_gap = sum(1 for d in deliverables if isinstance(d, dict) and d.get("required") and not d.get("exists"))

    metrics = {
        "files_count": len(project.files),
        "meetings_count": len(project.meetings),
        "tasks_total": len(tasks),
        "tasks_done": tasks_done,
        "risks_count": len(risks),
        "deliverables_gap": deliverables_gap,
    }

    # ── 智能研判（最新报告）────────────────────────────────────────────────
    analysis: dict | None = None
    if project.reports:
        latest_report = max(project.reports, key=lambda r: r.created_at)
        payload = safe_json_parse(latest_report.content_json or "{}", default={}, field_name="content_json")
        analysis = {
            "report_id": latest_report.id,
            "report_type": latest_report.report_type,
            "mode": latest_report.mode,
            "model_name": latest_report.model_name,
            "created_at": latest_report.created_at.isoformat() if latest_report.created_at else "",
            "project_basis": payload.get("project_basis", "") if isinstance(payload, dict) else "",
            "design_difficulties": payload.get("design_difficulties", []) if isinstance(payload, dict) else [],
            "project_summary": payload.get("project_summary", {}) if isinstance(payload, dict) else {},
            "risk_list": payload.get("risk_list", []) if isinstance(payload, dict) else [],
            "open_questions": payload.get("open_questions", []) if isinstance(payload, dict) else [],
            "technical_focus_cards": payload.get("technical_focus_cards", []) if isinstance(payload, dict) else [],
            "next_actions": payload.get("next_actions", []) if isinstance(payload, dict) else [],
        }

    # ── 最近会议纪要摘要 ────────────────────────────────────────────────────
    recent_meeting: dict | None = None
    if project.meetings:
        latest_meeting = max(project.meetings, key=lambda m: m.created_at)
        recent_meeting = _serialise_meeting_brief(latest_meeting)

    # ── 下一步待办（未完成任务前5）──────────────────────────────────────────
    next_actions = [
        _serialise_task(t)
        for t in tasks
        if t.status not in done_statuses
    ][:5]

    # ── 里程碑列表 ──────────────────────────────────────────────────────────
    milestones = safe_json_parse(project.milestones, default=[], field_name="milestones")
    if not isinstance(milestones, list):
        milestones = []

    # ── 可复用资产（基于知识库 FTS5 检索）───────────────────────────────────
    reusable_assets = []
    try:
        from app.retrieval import FTS5RetrievalEngine

        retrieval = FTS5RetrievalEngine(db_engine)
        search_query = f"{project.name} {project.city or ''} {project.project_type or ''}".strip()
        if search_query:
            similar_results = retrieval.search(search_query, top_k=5)
            reusable_assets = [
                {
                    "title": r["title"],
                    "content_preview": r["content"][:100],
                    "score": r["score"],
                    "chunk_id": r["chunk_id"],
                }
                for r in similar_results
            ]
    except Exception as exc:
        logger.warning("Reusable assets retrieval failed (non-fatal): %s", exc)

    return {
        "project": schemas.ProjectOut.model_validate(project).model_dump(mode="json"),
        "metrics": metrics,
        "analysis": analysis,
        "recent_meeting": recent_meeting,
        "next_actions": next_actions,
        "milestones": milestones,
        "risks": risks,
        "reusable_assets": reusable_assets,
    }


@router.patch("/{project_id}/client")
def update_project_client(project_id: str, payload: schemas.ClientUpdate, db: Session = Depends(get_db)):
    """更新甲方/客户信息（名称、联系方式、诉求）。"""
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value or "")
    db.commit()
    db.refresh(project)
    # 变更事件：甲方信息修改
    from ..services.event_engine import emit_change_event
    emit_change_event(
        db, project_id, "client_demands_updated",
        source_type="manual", source_id=None,
        affected_fields=list(update_data.keys()),
        description="更新甲方信息",
    )
    return schemas.ProjectOut.model_validate(project).model_dump(mode="json")


@router.patch("/{project_id}/milestones")
def update_project_milestones(project_id: str, payload: schemas.MilestonesUpdate, db: Session = Depends(get_db)):
    """更新里程碑列表。"""
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    project.milestones = safe_json_dump(payload.milestones, field_name="milestones") or "[]"
    db.commit()
    db.refresh(project)
    return safe_json_parse(project.milestones, default=[], field_name="milestones")


@router.delete("/{project_id}", response_model=schemas.ProjectDeleteOut)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    result = delete_project_library(db, project_id)
    if not result["deleted"]:
        raise HTTPException(status_code=404, detail="项目不存在")
    return result


@router.post("/{project_id}/upload", response_model=list[schemas.ProjectFileOut])
async def upload_project_files(project_id: str, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not files:
        raise HTTPException(status_code=400, detail="没有收到文件")
    target_dir = project_upload_dir(project_id)
    saved = []
    for upload in files:
        filename = Path(upload.filename or "uploaded-file").name
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_PROJECT_EXTS:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型：{filename}")
        content = await upload.read()
        target = target_dir / filename
        target.write_bytes(content)
        mirror_project_file(
            project_id,
            target,
            {"filename": filename, "filetype": ext.lstrip("."), "filesize": len(content)},
        )
        record = models.ProjectFile(
            project_id=project_id,
            filename=filename,
            filepath=str(target),
            filetype=ext.lstrip("."),
            filesize=len(content),
            parse_status="pending",
            analysis_status="pending",
        )
        db.add(record)
        saved.append(record)
    db.commit()
    for item in saved:
        db.refresh(item)
    # 变更事件：文件上传
    from ..services.event_engine import emit_change_event
    for item in saved:
        emit_change_event(
            db, project_id, "file_uploaded",
            source_type="file", source_id=str(item.id),
            description=f"上传文件: {item.filename}",
        )
    return saved


@router.post("/{project_id}/parse", response_model=list[schemas.ProjectFileOut])
def parse_project_files(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    parsed_files = []
    for file in project.files:
        if file.parse_status == "parsed":
            continue
        text, status = parse_document(Path(file.filepath))
        file.parsed_text = text
        file.parse_status = status
        file.analysis_status = "pending"
        mirror_project_parse(project_id, file.id, file.filename, text, status)
        parsed_files.append(file)
    db.commit()
    return parsed_files or project.files


@router.get("/{project_id}/files/{file_id}/preview")
def preview_project_file(project_id: str, file_id: str, db: Session = Depends(get_db)):
    file = db.scalar(
        select(models.ProjectFile).where(models.ProjectFile.id == file_id, models.ProjectFile.project_id == project_id)
    )
    if not file:
        raise HTTPException(status_code=404, detail="项目资料不存在")
    return {
        "id": file.id,
        "filename": file.filename,
        "parse_status": file.parse_status,
        "content": file.parsed_text or "",
    }


@router.post("/{project_id}/files/{file_id}/parse", response_model=schemas.ProjectFileOut)
def parse_one_project_file(project_id: str, file_id: str, db: Session = Depends(get_db)):
    file = db.scalar(
        select(models.ProjectFile).where(models.ProjectFile.id == file_id, models.ProjectFile.project_id == project_id)
    )
    if not file:
        raise HTTPException(status_code=404, detail="项目资料不存在")
    text, status = parse_document(Path(file.filepath))
    file.parsed_text = text
    file.parse_status = status
    file.analysis_status = "pending"
    mirror_project_parse(project_id, file.id, file.filename, text, status)
    db.commit()
    db.refresh(file)
    return file


@router.delete("/{project_id}/files/{file_id}")
def delete_project_file(project_id: str, file_id: str, db: Session = Depends(get_db)):
    file = db.scalar(
        select(models.ProjectFile).where(models.ProjectFile.id == file_id, models.ProjectFile.project_id == project_id)
    )
    if not file:
        raise HTTPException(status_code=404, detail="项目资料不存在")
    path = Path(file.filepath)
    managed_root = project_upload_dir(project_id).resolve()
    try:
        resolved = path.resolve()
        if resolved.is_relative_to(managed_root) and resolved.exists():
            resolved.unlink()
    except OSError:
        pass
    db.delete(file)
    db.commit()
    return {"deleted": True, "deleted_file_id": file_id}


@router.post("/{project_id}/analyze", response_model=schemas.ProjectAnalyzeOut)
async def analyze_project(payload: schemas.ProjectAnalyzeRequest, project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    files = project.files
    fallback_payload = mock_analysis_payload(project, files)
    analysis_payload = fallback_payload
    mode = "mock"
    try:
        prompt = (
            "请基于以下项目资料生成建筑设计项目分析 JSON。字段必须包含 "
            "project_basis、design_difficulties、timeline、team_requirements、knowledge_refs、tasks、next_actions。"
            "tasks 中每项必须包含 task_name、task_type、priority、owner_role、estimated_days、dependencies、risk_level、status、output_requirement。\n\n"
            f"项目：{project.name}\n"
            f"城市：{project.city}\n"
            f"类型：{project.project_type}\n"
            f"阶段：{project.phase}\n"
            f"描述：{project.description}\n\n"
            "文件内容摘要：\n"
            + "\n\n".join((file.parsed_text or "")[:2500] for file in files[:8])
        )
        deepseek_payload = await call_deepseek_json(prompt)
        if deepseek_payload:
            analysis_payload = normalize_analysis_payload(deepseek_payload, fallback_payload)
            analysis_payload["mode"] = "deepseek"
            mode = "deepseek"
        elif not settings.mock_mode:
            raise RuntimeError("DeepSeek 未返回有效分析结果")
    except Exception as exc:
        if not settings.mock_mode:
            raise HTTPException(status_code=502, detail=f"DeepSeek 分析失败：{exc}") from exc
        analysis_payload["mode"] = "mock"
        mode = "mock"
    if payload.auto_fetch_knowledge and not analysis_payload.get("knowledge_refs"):
        analysis_payload["knowledge_refs"] = fallback_payload.get("knowledge_refs", [])
    report = save_analysis_result(db, project, analysis_payload, mode)
    mirror_project_report(project_id, report.id, report.markdown, analysis_payload)
    project = crud.get_project(db, project_id)
    return {
        "report": report,
        "tasks": project.tasks if project else [],
        "timeline": project.timelines if project else [],
        "team_requirements": team_requirements_from_payload(analysis_payload),
        "knowledge_refs": project.knowledge_references if project else [],
    }


def _startup_response(report: models.ProjectReport) -> dict:
    payload = safe_json_parse(report.content_json or "{}", default={}, field_name="content_json")
    return {
        "report": schemas.ProjectReportOut.model_validate(report).model_dump(mode="json"),
        **payload,
    }


@router.post("/{project_id}/startup-analysis")
async def create_startup_analysis(
    project_id: str,
    payload: schemas.StartupAnalysisRequest = schemas.StartupAnalysisRequest(),
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if payload.refresh_knowledge:
        vault_path = Path(payload.vault_path or settings.default_vault_path)
        if not vault_path.exists() or not vault_path.is_dir():
            raise HTTPException(status_code=404, detail=f"Obsidian目录不存在：{vault_path}")
        scan_vault_directory(db, vault_path, clear_existing=False)
        project = crud.get_project(db, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
    try:
        result = await run_startup_analysis(db, project)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _startup_response(result["report"])


@router.get("/{project_id}/startup-analysis")
def get_startup_analysis(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    report = db.scalar(
        select(models.ProjectReport)
        .where(models.ProjectReport.project_id == project_id, models.ProjectReport.report_type == "startup_analysis")
        .order_by(models.ProjectReport.created_at.desc())
    )
    if not report:
        raise HTTPException(status_code=404, detail="还没有项目启动分析")
    return _startup_response(report)


@router.get("/{project_id}/mindmap")
def get_project_mindmap(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    report = db.scalar(
        select(models.ProjectReport)
        .where(models.ProjectReport.project_id == project_id, models.ProjectReport.report_type == "startup_analysis")
        .order_by(models.ProjectReport.created_at.desc())
    )
    if report:
        payload = safe_json_parse(report.content_json or "{}", default={}, field_name="content_json")
        return payload.get("mindmap_json") or {"title": "项目启动分析", "nodes": []}
    for meeting in project.meetings:
        if meeting.mindmap_json:
            return safe_json_parse(meeting.mindmap_json, default={}, field_name="mindmap_json")
    return {"title": "项目启动分析", "nodes": []}


@router.get("/{project_id}/tasks", response_model=list[schemas.ProjectTaskOut])
def project_tasks(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_project_sidecars(db, project)
    project = crud.get_project(db, project_id)
    return project.tasks if project else []


@router.post("/{project_id}/tasks", response_model=schemas.ProjectTaskOut, status_code=201)
def create_project_task(project_id: str, payload: schemas.ProjectTaskCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    task = models.ProjectTask(project_id=project_id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.put("/{project_id}/tasks/{task_id}", response_model=schemas.ProjectTaskOut)
def update_project_task(project_id: str, task_id: str, payload: schemas.ProjectTaskUpdate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    task = db.scalar(
        select(models.ProjectTask).where(
            models.ProjectTask.id == task_id,
            models.ProjectTask.project_id == project_id,
        )
    )
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{project_id}/tasks/{task_id}")
def delete_project_task(project_id: str, task_id: str, db: Session = Depends(get_db)):
    task = db.scalar(
        select(models.ProjectTask).where(models.ProjectTask.id == task_id, models.ProjectTask.project_id == project_id)
    )
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    db.delete(task)
    db.commit()
    return {"deleted": True, "deleted_task_id": task_id}


@router.put("/{project_id}/tasks/{task_id}/assignee", response_model=schemas.ProjectTaskOut)
def assign_project_task(
    project_id: str,
    task_id: str,
    payload: schemas.ProjectTaskAssigneeUpdate,
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    task = db.scalar(
        select(models.ProjectTask).where(
            models.ProjectTask.id == task_id,
            models.ProjectTask.project_id == project_id,
        )
    )
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if payload.assignee_id:
        exists = db.scalar(
            select(models.TeamAssignment).where(
                models.TeamAssignment.project_id == project_id,
                models.TeamAssignment.member_id == payload.assignee_id,
                models.TeamAssignment.member_type == payload.assignee_type,
            )
        )
        if not exists:
            raise HTTPException(status_code=400, detail="请先把该成员加入项目团队")
    task.assignee_type = payload.assignee_type
    task.assignee_id = payload.assignee_id
    task.assignee_name = payload.assignee_name
    if payload.assignee_name:
        task.owner_role = payload.assignee_name
    db.commit()
    db.refresh(task)
    return task


@router.get("/{project_id}/timeline", response_model=list[schemas.ProjectTimelineOut])
def project_timeline(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_project_sidecars(db, project)
    project = crud.get_project(db, project_id)
    return project.timelines if project else []


@router.post("/{project_id}/knowledge-refs", response_model=schemas.KnowledgeReferenceOut)
def create_knowledge_ref(project_id: str, payload: schemas.KnowledgeReferenceCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    ref = models.KnowledgeReference(project_id=project_id, **payload.model_dump())
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return ref


@router.post("/{project_id}/trigger-agent/{agent_id}", response_model=schemas.AgentRunOut)
def trigger_project_agent(
    project_id: str,
    agent_id: str,
    payload: schemas.AgentTriggerRequest = schemas.AgentTriggerRequest(),
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    context = {
        "trigger_type": payload.trigger_type,
        "context": payload.context_json,
        "project": {"id": project.id, "name": project.name, "phase": project.phase},
    }
    trigger = models.AgentTrigger(
        project_id=project.id,
        agent_id=agent_id,
        trigger_type=payload.trigger_type,
        context_json=safe_json_dump(context, field_name="context_json"),
        status="queued",
    )
    run = models.AgentRun(
        project_id=project.id,
        agent_id=agent_id,
        input_context=safe_json_dump(context, field_name="input_context"),
        output_json=safe_json_dump(
            {
                "mode": "mock",
                "message": "已触发 AI代理，结果将显示在 AI代理页面。",
                "next_step": "未来将从项目任务创建真实代理任务。",
            },
            field_name="output_json",
        ),
        status="queued",
    )
    db.add(trigger)
    db.add(run)
    db.commit()
    db.refresh(run)
    mirror_agent_run(project.id, run.id, run.agent_id, run.input_context, run.output_json, run.status)
    return run


@router.get("/{project_id}/agent-runs", response_model=list[schemas.AgentRunOut])
def project_agent_runs(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project.agent_runs


@router.delete("/{project_id}/agent-runs/{run_id}")
def delete_project_execution_run(project_id: str, run_id: str, db: Session = Depends(get_db)):
    run = db.scalar(
        select(models.AgentRun).where(
            models.AgentRun.id == run_id,
            models.AgentRun.project_id == project_id,
            models.AgentRun.agent_id == "project-execution",
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="执行台问答记录不存在")
    db.delete(run)
    db.commit()
    return {"deleted": True, "deleted_run_id": run_id}


@router.post("/{project_id}/execute", response_model=schemas.AgentRunOut)
async def execute_project_instruction(
    project_id: str,
    payload: schemas.ProjectExecuteRequest,
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return await run_project_execution(db, project, payload.instruction.strip())


@router.post("/{project_id}/team-plan", response_model=schemas.TeamPlanOut)
def create_team_plan(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return build_team_plan(db, project)


@router.get("/{project_id}/team-plan", response_model=list[schemas.TeamPlanOut])
def get_team_plan(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project.team_plans


@router.get("/{project_id}/meetings", response_model=list[schemas.ProjectMeetingOut])
def project_meetings(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project.meetings


def _parse_scheduled_at(value: str) -> Optional[datetime]:
    """将前端 datetime-local 字符串解析为 aware datetime。"""
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


@router.post("/{project_id}/meetings", response_model=schemas.ProjectMeetingOut)
def create_project_meeting(project_id: str, payload: schemas.ProjectMeetingCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    tencent = parse_tencent_meeting_result(payload.meeting_link)
    meeting = models.Meeting(
        project_id=project.id,
        title=payload.title,
        meeting_type=payload.meeting_type or "项目会议",
        date=_parse_scheduled_at(payload.scheduled_at),
        agenda=payload.agenda,
        recording_url=payload.meeting_link,
        tencent_join_url=tencent.get("join_url", ""),
        tencent_meeting_code=tencent.get("meeting_code", ""),
        tencent_meeting_id=tencent.get("meeting_id", ""),
        transcript=payload.transcript,
        status=payload.status if payload.status != "planned" else "scheduled",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


@router.delete("/{project_id}/meetings/{meeting_id}")
def delete_project_meeting(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    meeting = db.get(models.Meeting, meeting_id)
    if not meeting or meeting.project_id != project_id:
        raise HTTPException(status_code=404, detail="会议不存在")

    for indexed_path in (
        f"project-context/{project_id}/meetings/{meeting_id}.md",
        f"project-context/{project_id}/meeting-transcripts/{meeting_id}.md",
        f"project-deposits/{project_id}/meetings/{meeting_id}.md",
        f"project-deposits/{project_id}/meeting-transcripts/{meeting_id}.md",
    ):
        knowledge_file = db.scalar(select(models.KnowledgeFile).where(models.KnowledgeFile.filepath == indexed_path))
        if knowledge_file:
            db.execute(delete(models.KnowledgeChunk).where(models.KnowledgeChunk.file_id == knowledge_file.id))
            db.execute(delete(models.KnowledgeTag).where(models.KnowledgeTag.file_id == knowledge_file.id))
            db.execute(delete(models.KnowledgeLink).where(models.KnowledgeLink.file_id == knowledge_file.id))
            db.delete(knowledge_file)

    db.delete(meeting)
    db.commit()
    return {"deleted": True, "deleted_meeting_id": meeting_id}


@router.post("/{project_id}/meetings/tencent", response_model=schemas.ProjectMeetingOut)
def create_tencent_project_meeting(project_id: str, payload: schemas.TencentMeetingCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    start_time = payload.start_time
    end_time = payload.end_time
    if not start_time:
        raise HTTPException(status_code=400, detail="请填写会议开始时间")
    if not end_time:
        raise HTTPException(status_code=400, detail="请填写会议结束时间")
    try:
        tencent = schedule_tencent_meeting(payload.title, start_time, end_time)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"腾讯会议创建失败：{exc}") from exc
    link_lines = []
    if tencent.get("join_url"):
        link_lines.append(tencent["join_url"])
    if tencent.get("meeting_code"):
        link_lines.append(f"会议号：{tencent['meeting_code']}")
    if tencent.get("meeting_id"):
        link_lines.append(f"meeting_id：{tencent['meeting_id']}")
    if tencent.get("trace"):
        link_lines.append(f"X-Tc-Trace：{tencent['trace']}")
    meeting_date = None
    try:
        meeting_date = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except ValueError:
        meeting_date = None
    meeting = models.Meeting(
        project_id=project.id,
        title=payload.title,
        meeting_type="tencent",
        date=meeting_date,
        agenda=payload.agenda,
        recording_url="\n".join(link_lines),
        tencent_join_url=tencent.get("join_url", ""),
        tencent_meeting_code=tencent.get("meeting_code", ""),
        tencent_meeting_id=tencent.get("meeting_id", ""),
        status="scheduled",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


COMMUNICATION_TYPE_LABELS = {
    "phone": "电话",
    "wechat": "微信摘录",
    "email": "邮件摘要",
    "onsite": "现场沟通",
    "verbal": "口头沟通",
}


@router.post("/{project_id}/communications", response_model=schemas.CommunicationOut)
async def create_communication(project_id: str, payload: schemas.CommunicationCreate, db: Session = Depends(get_db)):
    """沟通记录轻量入口：复用 Meeting 模型，自动生成五段式纪要 + 甲方诉求转译。"""
    from app.meeting_engine import MeetingMinutesEngine, build_minutes_prompt
    from app.services.audio import clean_transcript_text
    from app.services.event_engine import emit_change_event
    from app.utils import utc_now

    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    comm_type = payload.communication_type.strip().lower()
    if comm_type not in COMMUNICATION_TYPE_LABELS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的沟通类型：{payload.communication_type}，支持：{', '.join(COMMUNICATION_TYPE_LABELS.keys())}",
        )

    raw_content = payload.content.strip()
    if len(raw_content) < 10:
        raise HTTPException(status_code=400, detail="沟通内容过短，请至少输入 10 个字符")

    cleaned = clean_transcript_text(raw_content)
    occurred_at = _parse_scheduled_at(payload.occurred_at) or utc_now()

    title = payload.title.strip()
    if not title:
        label = COMMUNICATION_TYPE_LABELS[comm_type]
        title = f"{label}记录 {occurred_at.strftime('%m-%d %H:%M')}"

    agenda_parts = []
    if payload.participants.strip():
        agenda_parts.append(f"参与人：{payload.participants.strip()}")
    agenda = "\n".join(agenda_parts)

    meeting = models.Meeting(
        project_id=project.id,
        title=title,
        meeting_type=comm_type,
        date=occurred_at,
        agenda=agenda,
        transcript=cleaned,
        transcription_source="manual",
        status="completed",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    project_context = {
        "name": project.name,
        "city": project.city,
        "project_type": project.project_type,
        "stage": project.phase,
        "client_name": project.client_name or "",
    }

    engine = MeetingMinutesEngine()
    rule_translations = engine.translate_client_demands(cleaned)

    prompt = build_minutes_prompt(cleaned, project_context)
    ai_response = None
    try:
        ai_response = await call_deepseek_json(prompt)
    except Exception as exc:
        logger.warning("DeepSeek 沟通纪要生成失败，使用模板：%s", exc)

    minutes = engine.generate_five_section_minutes(cleaned, project_context, ai_response)
    if not minutes.get("client_translation") and rule_translations:
        minutes["client_translation"] = rule_translations

    broadcast = engine.generate_broadcast_script(minutes)
    versions = engine.split_internal_external(minutes)

    # 持久化纪要到会议记录
    meeting.summary = minutes.get("meeting_content", "")
    meeting.minutes = safe_json_dump(minutes, field_name="minutes")
    meeting.mindmap_json = safe_json_dump(minutes, field_name="mindmap_json")
    meeting.next_actions_json = safe_json_dump(minutes.get("action_items", []), field_name="next_actions_json")
    meeting.todos = safe_json_dump(minutes.get("action_items", []), field_name="todos")
    meeting.status = "summarized"
    db.commit()
    db.refresh(meeting)

    emit_change_event(
        db, project_id, "communication_added",
        source_type="meeting", source_id=str(meeting.id),
        affected_fields=["meetings", "minutes", "client_translation"],
        description=f"新增沟通记录: {title} ({COMMUNICATION_TYPE_LABELS[comm_type]})",
    )

    return {
        "meeting": meeting,
        "minutes": minutes,
        "internal_version": versions["internal"],
        "external_version": versions["external"],
        "broadcast_script": broadcast,
        "rule_translations": rule_translations,
    }


@router.post("/{project_id}/meetings/{meeting_id}/sync-tencent-minutes", response_model=schemas.ProjectMeetingOut)
def sync_tencent_project_meeting_minutes(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    meeting = db.get(models.Meeting, meeting_id)
    if not meeting or meeting.project_id != project_id:
        raise HTTPException(status_code=404, detail="会议不存在")
    try:
        return sync_tencent_meeting_minutes(db, meeting)
    except TencentMinutesUnavailableError as exc:
        meeting.sync_status = "failed"
        meeting.sync_error = str(exc)
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        meeting.sync_status = "failed"
        meeting.sync_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"同步腾讯会议纪要失败：{exc}") from exc


@router.post("/{project_id}/meetings/{meeting_id}/summarize", response_model=schemas.ProjectMeetingOut)
async def summarize_project_meeting(
    project_id: str,
    meeting_id: str,
    payload: schemas.ProjectMeetingUpdate = schemas.ProjectMeetingUpdate(),
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    meeting = db.get(models.Meeting, meeting_id)
    if not meeting or meeting.project_id != project_id:
        raise HTTPException(status_code=404, detail="会议不存在")
    values = payload.model_dump(exclude_unset=True)
    if "meeting_link" in values:
        meeting.recording_url = values.pop("meeting_link") or ""
    values.pop("meeting_type", None)
    values.pop("scheduled_at", None)
    for key, value in values.items():
        setattr(meeting, key, value)
    db.commit()
    try:
        return await summarize_meeting(db, meeting)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/skill-cards", response_model=list[schemas.SkillCardOut])
def project_skill_cards(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project.skill_cards


@router.post("/{project_id}/skill-cards", response_model=schemas.SkillCardOut)
def create_project_skill_card(project_id: str, payload: schemas.SkillCardCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    card = models.SkillCard(
        project_id=project.id,
        card_type=payload.card_type,
        title=payload.title or payload.card_type,
        input_data=payload.input_data,
        input_json=safe_json_dump(payload.input_json, field_name="input_json"),
        output_data="{}",
        output_json="{}",
        markdown="",
        status="ready",
        source="manual",
        created_by=payload.created_by,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.post("/{project_id}/skill-cards/run", response_model=schemas.SkillCardOut)
def run_project_skill_card(project_id: str, payload: schemas.SkillCardRunRequest, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return run_skill_card(db, project, payload.card_type, payload.prompt)


@router.post("/{project_id}/agent-chat", response_model=schemas.AgentChatOut)
async def project_agent_chat(project_id: str, payload: schemas.AgentChatRequest, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return await run_agent_chat(db, project, payload.message, payload.skill_id)


@router.post("/{project_id}/assignments", response_model=schemas.ProjectAssignmentOut)
def create_project_assignment(project_id: str, payload: schemas.ProjectAssignmentCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    assignment = models.TeamAssignment(
        project_id=project.id,
        member_id=payload.assignee_id,
        member_type=payload.assignee_type,
        member_name=payload.assignee_name,
        role=payload.role,
        responsibilities=payload.responsibility,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.post("/{project_id}/meetings/generate-minutes")
async def generate_meeting_minutes(project_id: str, request: Request, db: Session = Depends(get_db)):
    """
    生成五段式会议纪要
    输入：transcript（手动粘贴转写文本，默认路径）
    """
    from app.meeting_engine import MeetingMinutesEngine, build_minutes_prompt

    body = await request.json()
    transcript = body.get("transcript", "")

    if not transcript.strip():
        return JSONResponse({"error": "请提供会议转写文本"}, status_code=400)

    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        return JSONResponse({"error": "项目不存在"}, status_code=404)

    project_context = {
        "name": project.name,
        "city": project.city,
        "project_type": project.project_type,
        "stage": project.phase,
        "client_name": "",
    }

    engine = MeetingMinutesEngine()

    # 规则层先做转译
    rule_translations = engine.translate_client_demands(transcript)

    # 构建 AI prompt
    prompt = build_minutes_prompt(transcript, project_context)

    # 调用 DeepSeek（如果可用）
    ai_response = None
    try:
        ai_result = await call_deepseek_json(prompt)
        if ai_result:
            ai_response = ai_result
    except Exception as e:
        logger.warning("DeepSeek call failed, using template: %s", e)

    # 生成五段式纪要
    minutes = engine.generate_five_section_minutes(transcript, project_context, ai_response)

    # 合并规则转译（如果AI没返回转译）
    if not minutes["client_translation"] and rule_translations:
        minutes["client_translation"] = rule_translations

    # 生成播报脚本
    broadcast = engine.generate_broadcast_script(minutes)

    # 分离内外版
    versions = engine.split_internal_external(minutes)

    return {
        "minutes": minutes,
        "internal_version": versions["internal"],
        "external_version": versions["external"],
        "broadcast_script": broadcast,
        "rule_translations": rule_translations,
        "status": "draft",
    }


@router.post("/{project_id}/meetings/{meeting_id}/confirm-minutes")
async def confirm_meeting_minutes(
    project_id: str, meeting_id: str, request: Request, db: Session = Depends(get_db)
):
    """人工审定后确认纪要为正式版，并回流知识库"""
    from app.database import serialized_write

    body = await request.json()
    confirmed_minutes = body.get("minutes", {})

    meeting = db.query(models.Meeting).filter_by(id=meeting_id, project_id=project_id).first()
    if not meeting:
        return JSONResponse({"error": "会议不存在"}, status_code=404)

    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        return JSONResponse({"error": "项目不存在"}, status_code=404)

    with serialized_write():
        meeting.todos = safe_json_dump(confirmed_minutes.get("action_items", []), "todos")
        meeting.next_actions_json = safe_json_dump(confirmed_minutes.get("action_items", []), "next_actions")
        meeting.mindmap_json = safe_json_dump(confirmed_minutes, "mindmap_json")
        meeting.summary = confirmed_minutes.get("meeting_content", meeting.summary)
        meeting.status = "summarized"

        # 待办回流任务看板
        for action in confirmed_minutes.get("action_items", []):
            task_name = (action.get("task", "") if isinstance(action, dict) else str(action))[:200]
            if not task_name:
                continue
            existing = db.query(models.ProjectTask).filter_by(
                project_id=project_id, task_name=task_name
            ).first()
            if not existing:
                priority = action.get("priority", "medium") if isinstance(action, dict) else "medium"
                assignee = action.get("assignee", "") if isinstance(action, dict) else ""
                new_task = models.ProjectTask(
                    project_id=project_id,
                    task_name=task_name,
                    status="todo",
                    priority=priority,
                    owner_role=assignee,
                    source_type="meeting",
                    source_id=meeting_id,
                )
                db.add(new_task)

        db.commit()

    # 变更事件：会议纪要确认
    from ..services.event_engine import emit_change_event
    from ..services.meeting_reflux import execute_meeting_reflux

    emit_change_event(
        db, project_id, "meeting_confirmed",
        source_type="meeting", source_id=str(meeting.id),
        description=f"确认会议纪要: {meeting.title}",
    )

    # 结构化内容自动回流：demand_translation / risks / todos → 项目状态
    from ..json_safety import safe_json_parse as _sjp
    minutes_json = _sjp(meeting.mindmap_json) if meeting.mindmap_json else {}
    if not isinstance(minutes_json, dict):
        minutes_json = {}
    reflux_summary = execute_meeting_reflux(db, project, meeting, minutes_json)

    return {
        "success": True,
        "message": "纪要已确认，待办已回流任务看板",
        "reflux_summary": reflux_summary,
    }


@router.get("/{project_id}/change-events")
def list_change_events(project_id: str, days: int = 30, db: Session = Depends(get_db)):
    """查询项目变更时间线"""
    from ..services.event_engine import get_project_change_timeline
    events = get_project_change_timeline(db, project_id, days=days)
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "source_type": e.source_type,
            "description": e.description,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "consumed_by_analysis": e.consumed_by_analysis,
        }
        for e in events
    ]


@router.get("/{project_id}/analysis-freshness")
def check_analysis_freshness(project_id: str, db: Session = Depends(get_db)):
    """检查分析新鲜度"""
    from ..services.event_engine import get_analysis_freshness
    return get_analysis_freshness(db, project_id)


@router.post("/{project_id}/incremental-analysis")
async def run_incremental_analysis_endpoint(
    project_id: str,
    db: Session = Depends(get_db),
):
    """执行增量分析"""
    from ..services.analysis import run_incremental_analysis
    result = await run_incremental_analysis(project_id, db)
    return result


@router.get("/{project_id}/obsidian-candidates", response_model=list[schemas.KnowledgeItemOut])
def list_obsidian_candidates(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return list(
        db.scalars(
            select(models.KnowledgeItem)
            .where(models.KnowledgeItem.project_id == project_id, models.KnowledgeItem.item_type == "obsidian_candidate")
            .order_by(models.KnowledgeItem.created_at.desc())
        )
    )


@router.post("/{project_id}/obsidian-candidates", response_model=schemas.KnowledgeItemOut)
def create_obsidian_candidate(
    project_id: str,
    payload: schemas.ObsidianCandidateCreate,
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    item = models.KnowledgeItem(
        project_id=project.id,
        source_file=payload.title or payload.item_type,
        item_type=payload.item_type,
        summary=payload.title,
        content=payload.content,
        tags=safe_json_dump(payload.tags, field_name="tags"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# ── 音频上传与转写端点 ───────────────────────────────────────────────────────


@router.post("/{project_id}/meetings/{meeting_id}/upload-audio")
async def upload_meeting_audio(
    project_id: str,
    meeting_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """\u4e0a\u4f20\u4f1a\u8bae\u97f3\u9891\u6587\u4ef6"""
    from app.config import get_settings
    from app.security import validate_path

    settings = get_settings()

    # \u6821\u9a8c\u6587\u4ef6\u683c\u5f0f
    allowed = [f.strip() for f in settings.audio_allowed_formats.split(",")]
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"\u4e0d\u652f\u6301\u7684\u97f3\u9891\u683c\u5f0f: {ext}\uff0c\u652f\u6301: {', '.join(allowed)}")

    # \u6821\u9a8c\u6587\u4ef6\u5927\u5c0f
    content = await file.read()
    max_bytes = settings.audio_max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(400, f"\u6587\u4ef6\u8fc7\u5927\uff0c\u6700\u5927 {settings.audio_max_size_mb}MB")

    # \u67e5\u627e\u4f1a\u8bae
    meeting = db.query(models.Meeting).filter(
        models.Meeting.id == meeting_id,
        models.Meeting.project_id == project_id,
    ).first()
    if not meeting:
        raise HTTPException(404, "\u4f1a\u8bae\u4e0d\u5b58\u5728")

    # \u4fdd\u5b58\u6587\u4ef6
    audio_dir = os.path.join(settings.upload_root, project_id, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    safe_filename = f"{meeting_id}_{int(datetime.now().timestamp())}{ext}"
    audio_path = os.path.join(audio_dir, safe_filename)
    validate_path(audio_path)

    with open(audio_path, "wb") as f:
        f.write(content)

    # \u66f4\u65b0 Meeting
    meeting.audio_file_path = audio_path
    db.commit()
    from app.services.event_engine import emit_change_event
    emit_change_event(
        db,
        project_id,
        "meeting_audio_uploaded",
        source_type="meeting",
        source_id=meeting_id,
        affected_fields=["meetings", "audio", "transcript"],
        new_snapshot={"filename": file.filename, "audio_path": audio_path, "size_bytes": len(content)},
        description=f"会议录音已上传: {file.filename}",
    )

    return {"message": "\u97f3\u9891\u4e0a\u4f20\u6210\u529f", "audio_path": audio_path, "size_mb": round(len(content) / 1024 / 1024, 2)}


@router.post("/{project_id}/meetings/{meeting_id}/transcribe")
async def transcribe_meeting_audio(
    project_id: str,
    meeting_id: str,
    db: Session = Depends(get_db),
):
    """\u8f6c\u5199\u4f1a\u8bae\u97f3\u9891"""
    from app.services.audio import transcribe_audio, clean_transcript_text

    meeting = db.query(models.Meeting).filter(
        models.Meeting.id == meeting_id,
        models.Meeting.project_id == project_id,
    ).first()
    if not meeting:
        raise HTTPException(404, "\u4f1a\u8bae\u4e0d\u5b58\u5728")
    if not meeting.audio_file_path:
        raise HTTPException(400, "\u8be5\u4f1a\u8bae\u5c1a\u672a\u4e0a\u4f20\u97f3\u9891\u6587\u4ef6")
    if not os.path.exists(meeting.audio_file_path):
        raise HTTPException(404, "\u97f3\u9891\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u53ef\u80fd\u5df2\u88ab\u5220\u9664")

    # \u6267\u884c\u8f6c\u5199
    try:
        result = await transcribe_audio(meeting.audio_file_path)
    except ValueError as exc:
        meeting.sync_status = "audio_transcribe_failed"
        meeting.sync_error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=f"音频已保存，但转写服务不可用：{exc}") from exc
    except Exception as exc:
        meeting.sync_status = "audio_transcribe_failed"
        meeting.sync_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"音频转写失败，可稍后重试：{exc}") from exc

    # \u6e05\u6d17\u5e76\u4fdd\u5b58
    cleaned_text = clean_transcript_text(result.text)
    meeting.transcript = cleaned_text
    meeting.audio_transcribed_at = datetime.now()
    meeting.transcription_source = result.source
    meeting.sync_status = "audio_transcribed"
    meeting.sync_error = ""
    db.commit()
    from app.services.event_engine import emit_change_event
    emit_change_event(
        db,
        project_id,
        "meeting_audio_transcribed",
        source_type="meeting",
        source_id=meeting_id,
        affected_fields=["meetings", "transcript", "okf", "analysis"],
        new_snapshot={"source": result.source, "segment_count": len(result.segments)},
        description=f"会议录音已转写: {meeting.title}",
    )

    return {
        "message": "\u8f6c\u5199\u5b8c\u6210",
        "transcript": cleaned_text,
        "duration_seconds": result.duration_seconds,
        "source": result.source,
        "segment_count": len(result.segments),
    }


@router.post("/{project_id}/meetings/{meeting_id}/paste-transcript")
async def paste_meeting_transcript(
    project_id: str,
    meeting_id: str,
    body: dict,
    db: Session = Depends(get_db),
):
    """\u7c98\u8d34\u5e76\u6e05\u6d17\u4f1a\u8bae\u8f6c\u5199\u6587\u672c"""
    from app.services.audio import clean_transcript_text

    raw_text = body.get("text", "")
    if not raw_text or len(raw_text.strip()) < 10:
        raise HTTPException(400, "\u6587\u672c\u5185\u5bb9\u592a\u77ed")

    meeting = db.query(models.Meeting).filter(
        models.Meeting.id == meeting_id,
        models.Meeting.project_id == project_id,
    ).first()
    if not meeting:
        raise HTTPException(404, "\u4f1a\u8bae\u4e0d\u5b58\u5728")

    cleaned = clean_transcript_text(raw_text)
    meeting.transcript = cleaned
    meeting.transcription_source = "manual"
    db.commit()

    return {
        "message": "文本已保存",
        "cleaned_text": cleaned,
        "original_length": len(raw_text),
        "cleaned_length": len(cleaned),
    }


# ── 块7 知识增强推荐 API ─────────────────────────────────────────────


@router.get("/{project_id}/recommendations")
def get_project_recommendations(
    project_id: str,
    trigger: str,
    transcript_text: Optional[str] = None,
    card_type: Optional[str] = None,
    file_names: Optional[str] = None,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    """获取知识推荐。

    Args:
        project_id: 项目 ID
        trigger: 触发点类型，有效值：analysis / okf_refresh / meeting / review / ppt / archive
        transcript_text: 会议场景下传入转写文本（可选）
        card_type: OKF 场景下传入卡片类型（可选）
        file_names: 归档场景下传入文件名列表，逗号分隔（可选）
        limit: 最多返回条数，默认 5
    """
    from app.services.knowledge_enhancer import get_recommendations, VALID_TRIGGERS
    from dataclasses import asdict

    if trigger not in VALID_TRIGGERS:
        raise HTTPException(
            status_code=400,
            detail=f"无效的触发点类型: '{trigger}'。有效值：{sorted(VALID_TRIGGERS)}",
        )

    safe_limit = max(1, min(limit, 20))

    kwargs = {}
    if transcript_text is not None:
        kwargs["transcript_text"] = transcript_text
    if card_type is not None:
        kwargs["card_type"] = card_type
    if file_names is not None:
        kwargs["file_names"] = [f.strip() for f in file_names.split(",") if f.strip()]

    try:
        result = get_recommendations(db, project_id, trigger, limit=safe_limit, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("知识推荐失败 project=%s trigger=%s: %s", project_id, trigger, e)
        raise HTTPException(status_code=500, detail="知识推荐服务暂时不可用")

    return {
        "project_id": project_id,
        "trigger": result.trigger,
        "recommendations": [
            {
                "title": item.title,
                "content_preview": item.content_preview,
                "source_type": item.source_type,
                "source_id": item.source_id,
                "source_path": item.source_path,
                "hit_reason": item.hit_reason,
                "relevance_score": item.relevance_score,
            }
            for item in result.recommendations
        ],
        "query_keywords": result.query_keywords,
        "total": len(result.recommendations),
        "generated_at": result.generated_at,
    }
