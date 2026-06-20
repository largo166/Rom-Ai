"""会议纪要自动回流 - 让会议结果进入项目循环"""
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Meeting, Project, ProjectTask, SkillCard
from ..json_safety import safe_json_dump, safe_json_parse
from .event_engine import emit_change_event


def reflux_demand_translation(
    db: Session, project: Project, demand_translations: list[dict]
) -> list[dict]:
    """将甲方诉求转译结果回流到 Project.client_demands

    返回新增的诉求列表（去重后）
    """
    existing_demands = safe_json_parse(project.client_demands) if project.client_demands else []
    if not isinstance(existing_demands, list):
        existing_demands = []

    # 提取现有诉求的 raw 文本做去重
    existing_raws = {d.get("raw", "").strip() for d in existing_demands if isinstance(d, dict)}

    new_demands = []
    for item in demand_translations:
        if not isinstance(item, dict):
            continue
        raw = (item.get("raw") or "").strip()
        if not raw or raw in existing_raws:
            continue
        new_demand = {
            "raw": raw,
            "translation": item.get("translation", ""),
            "design_response": item.get("design_response", ""),
            "confidence": item.get("confidence", "medium"),
            "category": item.get("category", ""),
            "source": "meeting",
        }
        new_demands.append(new_demand)
        existing_raws.add(raw)

    if new_demands:
        updated = existing_demands + new_demands
        project.client_demands = safe_json_dump(updated)
        db.flush()

    return new_demands


def reflux_risks(
    db: Session, project: Project, risks: list
) -> list[str]:
    """将新风险回流到 Project.risk_summary

    返回新增的风险列表（去重后）
    """
    existing_risks = safe_json_parse(project.risk_summary) if project.risk_summary else []
    if not isinstance(existing_risks, list):
        existing_risks = []

    # 简单去重：完全相同的文本
    existing_set = {str(r).strip() for r in existing_risks}

    new_risks = []
    for risk in risks:
        risk_text = str(risk).strip()
        if risk_text and risk_text not in existing_set:
            new_risks.append(risk_text)
            existing_set.add(risk_text)

    if new_risks:
        updated = existing_risks + new_risks
        project.risk_summary = safe_json_dump(updated)
        db.flush()

    return new_risks


def reflux_tasks(
    db: Session, project: Project, meeting: Meeting, todos: list[dict]
) -> list[ProjectTask]:
    """将待办回流为 ProjectTask（标记来源为会议）

    返回新创建的任务列表
    """
    created_tasks = []
    for todo in todos:
        if not isinstance(todo, dict):
            continue
        title = (todo.get("title") or todo.get("task_name") or todo.get("task", "")).strip()
        if not title:
            continue

        # 检查是否已存在同名任务（避免重复创建）
        existing = (
            db.query(ProjectTask)
            .filter(
                ProjectTask.project_id == project.id,
                ProjectTask.task_name == title,
            )
            .first()
        )
        if existing:
            continue

        task = ProjectTask(
            project_id=project.id,
            task_name=title,
            task_type="meeting_action",
            owner_role=todo.get("owner", todo.get("assignee", "")),
            priority=todo.get("priority", "medium"),
            status=todo.get("status", "todo"),
            source_type="meeting",
            source_id=meeting.id,
        )
        db.add(task)
        created_tasks.append(task)

    if created_tasks:
        db.flush()

    return created_tasks


def check_okf_staleness(
    db: Session, project: Project, meeting_content: dict
) -> list[str]:
    """检测哪些 SkillCard 可能因本次会议内容而需要更新

    返回可能过期的 card_type 列表
    """
    stale_types: list[str] = []

    # 获取项目的 SkillCard
    skill_cards = db.query(SkillCard).filter(SkillCard.project_id == project.id).all()

    if not skill_cards:
        return stale_types

    demand_translations = meeting_content.get("demand_translation", [])
    risks = meeting_content.get("risks", [])

    existing_types = {sc.card_type for sc in skill_cards}

    # 1. 有新的甲方诉求 → technical_focus 可能需要更新
    if demand_translations and "technical_focus" in existing_types:
        stale_types.append("technical_focus")

    # 2. 有新风险 → task_breakdown 可能需要调整
    if risks and "task_breakdown" in existing_types:
        stale_types.append("task_breakdown")

    # 3. 进度/工期类诉求 → task_breakdown 需更新
    for item in demand_translations:
        if isinstance(item, dict) and item.get("category") in ("进度", "节奏"):
            if "task_breakdown" not in stale_types and "task_breakdown" in existing_types:
                stale_types.append("task_breakdown")
            break

    return stale_types


def execute_meeting_reflux(
    db: Session, project: Project, meeting: Meeting, minutes_content: dict
) -> dict:
    """执行完整的会议纪要回流流程

    minutes_content 是纪要的 JSON 解析结果，包含：
    demand_translation, risks, todos / action_items 等字段

    返回回流摘要
    """
    demand_translations = minutes_content.get("demand_translation", [])
    risks = minutes_content.get("risks", [])
    # 兼容 todos 和 action_items 两种字段名
    todos = minutes_content.get("todos", minutes_content.get("action_items", []))

    # 1. 甲方诉求回流
    new_demands = reflux_demand_translation(db, project, demand_translations)

    # 2. 风险回流
    new_risks = reflux_risks(db, project, risks)

    # 3. 任务回流
    new_tasks = reflux_tasks(db, project, meeting, todos)

    # 4. OKF 过期检测
    stale_cards = check_okf_staleness(db, project, minutes_content)

    # 5. 生成变更事件
    if new_demands:
        emit_change_event(
            db,
            project.id,
            "client_demands_updated",
            source_type="meeting",
            source_id=meeting.id,
            affected_fields=["client_demands"],
            new_snapshot={"added_demands": new_demands},
            description=f"会议纪要回流：新增 {len(new_demands)} 条甲方诉求",
        )

    if new_risks:
        emit_change_event(
            db,
            project.id,
            "risk_updated",
            source_type="meeting",
            source_id=meeting.id,
            affected_fields=["risk_summary"],
            new_snapshot={"added_risks": new_risks},
            description=f"会议纪要回流：新增 {len(new_risks)} 条风险",
        )

    if stale_cards:
        emit_change_event(
            db,
            project.id,
            "okf_stale",
            source_type="meeting",
            source_id=meeting.id,
            new_snapshot={"stale_skill_types": stale_cards},
            description=f"检测到 {len(stale_cards)} 个技能卡可能需要刷新",
        )

    db.commit()

    return {
        "demands_added": len(new_demands),
        "risks_added": len(new_risks),
        "tasks_created": len(new_tasks),
        "okf_stale_cards": stale_cards,
    }
