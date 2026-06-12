from pathlib import Path
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.cloud import mirror_agent_run, mirror_project_file, mirror_project_parse, mirror_project_report
from app.config import settings
from app.database import get_db
from app.services import (
    SUPPORTED_PROJECT_EXTS,
    build_team_plan,
    call_deepseek_json,
    delete_project_library,
    ensure_project_sidecars,
    mock_analysis_payload,
    normalize_analysis_payload,
    parse_document,
    project_upload_dir,
    run_project_execution,
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
    except Exception:
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
    payload = json.loads(report.content_json or "{}")
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
    result = await run_startup_analysis(db, project)
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
        payload = json.loads(report.content_json or "{}")
        return payload.get("mindmap_json") or {"title": "项目启动分析", "nodes": []}
    for meeting in project.meetings:
        if meeting.mindmap_json:
            return json.loads(meeting.mindmap_json)
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
        context_json=json.dumps(context, ensure_ascii=False),
        status="queued",
    )
    run = models.AgentRun(
        project_id=project.id,
        agent_id=agent_id,
        input_context=json.dumps(context, ensure_ascii=False),
        output_json=json.dumps(
            {
                "mode": "mock",
                "message": "已触发 AI代理，结果将显示在 AI代理页面。",
                "next_step": "未来将从项目任务创建真实代理任务。",
            },
            ensure_ascii=False,
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


@router.post("/{project_id}/meetings", response_model=schemas.ProjectMeetingOut)
def create_project_meeting(project_id: str, payload: schemas.ProjectMeetingCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    meeting = models.Meeting(
        project_id=project.id,
        title=payload.title,
        agenda=payload.agenda,
        recording_url=payload.meeting_link,
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

    indexed_path = f"project-deposits/{project_id}/meetings/{meeting_id}.md"
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
        date=meeting_date,
        agenda=payload.agenda,
        recording_url="\n".join(link_lines),
        status="scheduled",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


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
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
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
        input_json=json.dumps(payload.input_json, ensure_ascii=False),
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
        tags=json.dumps(payload.tags, ensure_ascii=False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
