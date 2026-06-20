"""analysis.py — 启动分析、DeepSeek 调用、分析结果保存"""
import json
import re
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.json_safety import safe_json_dump, safe_json_parse
from app.utils import utc_now, utc_now_iso
from app.services.context import deposit_startup_analysis_to_knowledge
from app.services.cross_project import collect_cross_project_experience
from app.services.knowledge import search_knowledge, _refs_from_chunks


# ──────────────────────────── DeepSeek 调用 ────────────────────────────

async def call_deepseek_json(prompt: str) -> dict[str, Any]:
    if settings.mock_mode:
        return {}
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"}
    body = {
        "model": settings.deepseek_model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "你是建筑设计项目分析助手。只输出 JSON，不要输出 Markdown。字段必须稳定，缺失信息标注为'资料未提供，需确认'。不引用任何非当前项目的具体项目名、甲方名或城市名——所有项目信息均由 user message 运行时注入。",
            },
            {"role": "user", "content": prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"{settings.deepseek_base_url.rstrip('/')}/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    parsed = safe_json_parse(match.group(0), default={}, field_name="deepseek_json_extract")
    return parsed


async def call_deepseek_text(prompt: str, system_prompt: str) -> str:
    if settings.mock_mode:
        return ""
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"}
    body = {
        "model": settings.deepseek_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"{settings.deepseek_base_url.rstrip('/')}/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def parse_deepseek_models(payload: dict[str, Any]) -> list[dict[str, str]]:
    models_list = []
    for item in payload.get("data", []):
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        models_list.append({"id": model_id, "owned_by": str(item.get("owned_by") or "")})
    return models_list


async def list_deepseek_models() -> list[dict[str, str]]:
    if settings.mock_mode:
        return []
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{settings.deepseek_base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        return parse_deepseek_models(response.json())


# ──────────────────────────── 分析结果 ────────────────────────────

def mock_analysis_payload(project: models.Project, files: list[models.ProjectFile]) -> dict[str, Any]:
    completeness = "低" if not files else "中"
    tasks = [
        {
            "task_name": "宋式展示区归家动线策略",
            "task_type": "策略分析",
            "priority": "高",
            "owner_role": "主创设计师",
            "estimated_days": 3,
            "dependencies": ["T001"],
            "risk_level": "中",
            "status": "todo",
            "output_requirement": "输出动线分析图、策略文本、汇报PPT结构。",
        },
        {
            "task_name": "社区礼序界面与门头尺度校准",
            "task_type": "立面研究",
            "priority": "高",
            "owner_role": "立面负责人",
            "estimated_days": 4,
            "dependencies": ["宋式展示区归家动线策略"],
            "risk_level": "中",
            "status": "todo",
            "output_requirement": "输出门头比例、材质建议和节点风险说明。",
        },
        {
            "task_name": "展示区景观节点与室内到访体验衔接",
            "task_type": "协同设计",
            "priority": "中",
            "owner_role": "景观接口",
            "estimated_days": 2,
            "dependencies": ["宋式展示区归家动线策略"],
            "risk_level": "低",
            "status": "todo",
            "output_requirement": "输出景观节点清单、室内接口条件和体验动线说明。",
        },
    ]
    timeline = [
        {
            "stage_name": "概念方案阶段",
            "start_day": 1,
            "end_day": 7,
            "milestone": "概念方案汇报",
            "dependencies": [],
            "risk_note": "甲方决策周期不确定。",
        },
        {
            "stage_name": "展示区深化阶段",
            "start_day": 8,
            "end_day": 14,
            "milestone": "展示区动线与界面确认",
            "dependencies": ["概念方案阶段"],
            "risk_note": "景观、室内、立面接口需要同步确认。",
        },
        {
            "stage_name": "汇报整合阶段",
            "start_day": 15,
            "end_day": 18,
            "milestone": "PPT与图像成果交付",
            "dependencies": ["展示区深化阶段"],
            "risk_note": "素材版本与甲方关注点可能发生变化。",
        },
    ]
    team_requirements = {
        "total_headcount": 5,
        "roles": [
            {"role": "项目负责人", "count": 1, "skills": ["项目管理", "甲方沟通"], "intensity": "全职"},
            {"role": "主创设计师", "count": 1, "skills": ["宋式风格", "展示区设计"], "intensity": "全职"},
            {"role": "立面负责人", "count": 1, "skills": ["比例控制", "材料策略"], "intensity": "阶段投入"},
            {"role": "景观接口", "count": 1, "skills": ["归家动线", "节点体验"], "intensity": "阶段投入"},
            {"role": "汇报助理", "count": 1, "skills": ["PPT结构", "图像提示词"], "intensity": "阶段投入"},
        ],
    }
    knowledge_refs = [
        {
            "source_file": "宋式社区方法论.md",
            "source_path": "Obsidian Vault/方法/宋式社区方法论.md",
            "chunk_id": "mock-song-community-001",
            "quote": "宋式展示区应强调归家动线的礼仪感，以门庭、院落、廊下空间形成连续体验。",
            "relevance_score": 0.92,
        },
        {
            "source_file": "展示区体验动线清单.md",
            "source_path": "Obsidian Vault/方法/展示区体验动线清单.md",
            "chunk_id": "mock-arrival-002",
            "quote": "首开展示区需要把车行到达、步行归家、接待转换和样板间参观整合为一条可讲述的路径。",
            "relevance_score": 0.86,
        },
    ]
    return {
        "mode": "mock",
        "project_basis": {
            "project_type": project.project_type or "待确认",
            "phase": project.phase or "待确认",
            "资料完整度": completeness,
            "缺失信息": ["规划条件细则", "成本目标", "甲方决策边界"] if not files else ["成本目标", "关键节点时间"],
            "综合风险等级": "中",
        },
        "design_difficulties": {
            "技术难点": ["需要尽快核对指标、总图边界、产品组合和消防/日照等基础约束。"],
            "协调难点": ["建筑、景观、室内和报规口径需要统一，避免汇报阶段反复返工。"],
            "规范难点": ["消防、日照、停车和无障碍需要在强排阶段提前校核。"],
            "甲方决策难点": ["需要明确产品档次、立面成本和展示区范围。"],
            "成本与落地难点": ["立面材料、景观节点和公区精装需要控制落地成本。"],
            "后续深化风险点": ["资料不完整会影响任务拆解、周期判断和团队配置。"],
        },
        "timeline_summary": {
            "总体推进周期": "约 28-42 天（Mock，需要人工校准）",
            "概念方案阶段": "5-7 天",
            "强排 / 总图阶段": "7-10 天",
            "户型与产品阶段": "5-8 天",
            "立面与风格阶段": "7-10 天",
            "景观 / 室内 / 精装协同阶段": "5-8 天",
            "报规或汇报成果阶段": "3-5 天",
            "关键路径": ["规划条件确认", "强排稳定", "立面方向锁定", "汇报成果整合"],
            "里程碑节点": ["概念方向会", "强排评审", "立面评审", "最终汇报"],
            "可能延误点": ["资料缺失", "甲方反复", "多专业接口不同步"],
        },
        "timeline": timeline,
        "staffing": {
            "项目负责人 / PM": "1人",
            "主创设计师": "1人",
            "总图负责人": "1人",
            "户型负责人": "1人",
            "立面负责人": "1人",
            "景观接口": "0.5人",
            "室内接口": "0.5人",
            "后期 / 报规接口": "0.5人",
            "AI辅助人员": "1人",
            "建议人数规模": "5-7人等效投入",
            "每类人员技能要求": ["强排经验", "产品定位", "立面落地", "汇报组织"],
            "各阶段人员投入强度": "前期 PM/总图高，汇报前主创/立面/汇报助理高。",
        },
        "team_requirements": team_requirements,
        "knowledge_refs": knowledge_refs,
        "tasks": tasks,
        "next_actions": [
            "补齐规划条件、红线、指标和甲方任务书。",
            "建立项目资料目录并标注版本。",
            "先做强排风险清单，再进入立面风格推演。",
            "明确展示区、首开区和汇报成果范围。",
            "把关键问题提交甲方形成一次决策会。",
        ],
    }


def analysis_to_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# 项目分析报告（{payload.get('mode', 'mock')}）"]
    for section, value in payload.items():
        if section == "mode":
            continue
        lines.append(f"\n## {section}")
        if isinstance(value, dict):
            for key, item in value.items():
                rendered = json.dumps(item, ensure_ascii=False) if not isinstance(item, str) else item
                lines.append(f"- **{key}**：{rendered}")
        elif isinstance(value, list):
            for item in value:
                rendered = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else item
                lines.append(f"- {rendered}")
        else:
            lines.append(str(value))
    return "\n".join(lines)


def normalize_analysis_payload(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = {**fallback, **payload}
    for key in ("tasks", "timeline", "knowledge_refs"):
        if not isinstance(merged.get(key), list) or not merged[key]:
            merged[key] = fallback.get(key, [])
    if not isinstance(merged.get("team_requirements"), dict):
        merged["team_requirements"] = fallback.get("team_requirements", {"total_headcount": 0, "roles": []})
    return merged


def save_analysis_result(db: Session, project: models.Project, payload: dict[str, Any], mode: str) -> models.ProjectReport:
    report = models.ProjectReport(
        project_id=project.id,
        report_type="project_analysis",
        content_json=safe_json_dump(payload, field_name="content_json"),
        markdown=analysis_to_markdown(payload),
        model_name=settings.deepseek_model if mode == "deepseek" else "mock",
        mode=mode,
    )
    db.add(report)
    db.execute(delete(models.ProjectTask).where(models.ProjectTask.project_id == project.id))
    db.execute(delete(models.ProjectTimeline).where(models.ProjectTimeline.project_id == project.id))
    db.execute(delete(models.KnowledgeReference).where(models.KnowledgeReference.project_id == project.id))
    for item in payload.get("tasks", []):
        db.add(
            models.ProjectTask(
                project_id=project.id,
                task_name=item.get("task_name", ""),
                task_type=item.get("task_type", ""),
                priority=item.get("priority", "medium"),
                owner_role=item.get("owner_role", ""),
                estimated_days=int(item.get("estimated_days") or 1),
                dependencies=safe_json_dump(item.get("dependencies") or [], field_name="task_dependencies"),
                risk_level=item.get("risk_level", "medium"),
                status=item.get("status", "todo"),
                output_requirement=item.get("output_requirement", ""),
            )
        )
    for item in payload.get("timeline", []):
        db.add(
            models.ProjectTimeline(
                project_id=project.id,
                stage_name=item.get("stage_name", ""),
                start_day=int(item.get("start_day") or 1),
                end_day=int(item.get("end_day") or item.get("start_day") or 1),
                milestone=item.get("milestone", ""),
                dependencies=safe_json_dump(item.get("dependencies") or [], field_name="task_dependencies"),
                risk_note=item.get("risk_note", ""),
            )
        )
    for item in payload.get("knowledge_refs", []):
        db.add(
            models.KnowledgeReference(
                project_id=project.id,
                source_file=item.get("source_file", ""),
                source_path=item.get("source_path", ""),
                chunk_id=item.get("chunk_id", ""),
                quote=item.get("quote", ""),
                relevance_score=float(item.get("relevance_score") or 0),
            )
        )
    db.commit()
    db.refresh(report)
    return report


def ensure_project_sidecars(db: Session, project: models.Project) -> None:
    if project.tasks and project.timelines:
        return
    payload = mock_analysis_payload(project, project.files)
    save_analysis_result(db, project, payload, "mock")
    db.refresh(project)


def team_requirements_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("team_requirements")
    if isinstance(value, dict):
        return value
    return {"total_headcount": 0, "roles": []}


# ──────────────────────────── 启动分析 ────────────────────────────

def build_startup_analysis_payload(
    project: models.Project,
    chunks: list[models.KnowledgeChunk],
    cross_project_refs: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    refs = _refs_from_chunks(chunks)
    cross_project_refs = cross_project_refs or []
    ref_names = [ref["source_file"] for ref in refs[:6]]
    description = project.description or "暂无项目描述，需由项目经理补充业主诉求、规模、阶段和交付目标。"
    technical_focus_cards = [
        {
            "title": "技术卡_日照计算",
            "dimension": "日照",
            "summary": "启动阶段应确认当地日照规则、分析口径、遮挡边界和是否已有日照复核成果。",
            "checkpoints": ["大寒日/冬至日口径", "被遮挡对象", "楼栋间距", "复核图纸版本"],
            "source_refs": ref_names,
            "manual_confirm": "需要人工确认当地规划部门采用的日照计算口径。",
        },
        {
            "title": "技术卡_退界要求",
            "dimension": "退界",
            "summary": "优先核对红线、道路、邻地、消防登高面及地下边界退距。",
            "checkpoints": ["用地红线", "道路退距", "邻地退距", "地下室边界", "消防登高面"],
            "source_refs": ref_names,
            "manual_confirm": "需要以规划条件或设计任务书为准。",
        },
        {
            "title": "技术卡_面积计算",
            "dimension": "面积",
            "summary": "明确计容/不计容、赠送面积、架空层、人防、地下室和配套用房计算方式。",
            "checkpoints": ["计容总建面", "可售面积", "地下室", "架空层", "配套用房", "人防面积"],
            "source_refs": ref_names,
            "manual_confirm": "需要和当地面积测绘/报规口径交叉确认。",
        },
        {
            "title": "技术卡_消防风险",
            "dimension": "消防",
            "summary": "强排前置检查消防车道、登高场地、间距、防火分区和地下车库组织。",
            "checkpoints": ["消防车道", "登高场地", "防火间距", "地下车库", "疏散组织"],
            "source_refs": ref_names,
            "manual_confirm": "需要专业负责人复核。",
        },
        {
            "title": "技术卡_规划条件",
            "dimension": "规划",
            "summary": "项目启动必须锁定容积率、限高、密度、绿地率、停车、配套和地块边界。",
            "checkpoints": ["容积率", "限高", "建筑密度", "绿地率", "停车配比", "配套要求"],
            "source_refs": ref_names,
            "manual_confirm": "缺规划条件时，不应进入最终任务拆解。",
        },
        {
            "title": "技术卡_报批风险",
            "dimension": "报批",
            "summary": "识别需要提前沟通的规划、消防、人防、面积、日照和专家会风险。",
            "checkpoints": ["规划沟通", "消防审查", "人防口径", "面积测算", "日照复核", "专家会"],
            "source_refs": ref_names,
            "manual_confirm": "需要项目经理形成待业主确认清单。",
        },
    ]
    task_breakdown = [
        {
            "task_name": "项目启动资料完整性检查",
            "task_type": "启动检查",
            "priority": "高",
            "owner_role": "项目经理",
            "estimated_days": 1,
            "dependencies": [],
            "risk_level": "中",
            "status": "todo",
            "output_requirement": "形成资料缺口表，确认规划条件、红线、任务书和历史参考资料。",
        },
        {
            "task_name": "历史项目技术复用提取",
            "task_type": "知识复用",
            "priority": "高",
            "owner_role": "AI资料管理员",
            "estimated_days": 1,
            "dependencies": ["项目启动资料完整性检查"],
            "risk_level": "中",
            "status": "todo",
            "output_requirement": "输出日照、退界、面积、消防、规划、报批六类技术卡。",
        },
        {
            "task_name": "启动会议程与业主确认清单",
            "task_type": "会议推进",
            "priority": "高",
            "owner_role": "项目经理",
            "estimated_days": 1,
            "dependencies": ["历史项目技术复用提取"],
            "risk_level": "低",
            "status": "todo",
            "output_requirement": "形成启动会议程、待确认问题和下一步责任人。",
        },
        {
            "task_name": "项目启动汇报PPT结构",
            "task_type": "汇报组织",
            "priority": "中",
            "owner_role": "AI汇报助理",
            "estimated_days": 2,
            "dependencies": ["启动会议程与业主确认清单"],
            "risk_level": "中",
            "status": "todo",
            "output_requirement": "输出面向业主的PPT目录和每页核心表达。",
        },
    ]
    meeting_agenda = [
        "确认项目背景、区位、规模、设计阶段和业主诉求。",
        "核对规划条件、红线、日照、退界、面积计算和消防/报批资料缺口。",
        "复用历史项目经验，明确哪些规则可参考、哪些必须重新确认。",
        "确认本轮交付物、责任人和时间节点。",
        "形成下次会议前的待办和业主决策事项。",
    ]
    ppt_outline = [
        {"page": 1, "title": "项目启动背景", "content": "项目基本信息、业主诉求、当前阶段。"},
        {"page": 2, "title": "资料完整度与缺口", "content": "已上传资料、缺失资料、需确认来源。"},
        {"page": 3, "title": "历史项目技术复用", "content": "日照、退界、面积、消防、规划、报批六类重点。"},
        {"page": 4, "title": "启动阶段任务拆解", "content": "任务、负责人、优先级、交付物。"},
        {"page": 5, "title": "风险与下一步", "content": "未决问题、业主决策事项、下一次会议。"},
    ]
    risk_list = [
        "规划条件、红线或任务书缺失会导致任务拆解偏差。",
        "日照、退界、面积计算口径必须以当地正式要求为准。",
        "历史项目只能作为复用参考，不能替代本项目审批依据。",
        "若会议结论不回写任务看板，项目经理后续追踪会断链。",
    ]
    open_questions = [
        "业主本轮最关心的是进度、产品定位、成本还是报批风险？",
        "是否已有正式规划条件、红线和设计任务书？",
        "本项目是否需要先做强排可行性或日照快速复核？",
        "启动会后哪些事项需要业主书面确认？",
    ]
    mindmap_json = {
        "title": "项目启动分析",
        "nodes": [
            {
                "id": "project",
                "label": project.name,
                "children": [
                    {
                        "id": "technical",
                        "label": "技术重点",
                        "children": [{"id": card["dimension"], "label": card["dimension"]} for card in technical_focus_cards],
                    },
                    {
                        "id": "tasks",
                        "label": "任务拆解",
                        "children": [{"id": item["task_name"], "label": item["task_name"]} for item in task_breakdown],
                    },
                    {
                        "id": "meeting",
                        "label": "启动会",
                        "children": [{"id": str(idx), "label": item} for idx, item in enumerate(meeting_agenda, start=1)],
                    },
                    {
                        "id": "ppt",
                        "label": "PPT结构",
                        "children": [{"id": str(item["page"]), "label": item["title"]} for item in ppt_outline],
                    },
                ],
            }
        ],
    }
    return {
        "mode": "mock" if settings.mock_mode else "local_workflow",
        "project_summary": {
            "name": project.name,
            "city": project.city,
            "project_type": project.project_type,
            "phase": project.phase,
            "description": description,
            "knowledge_refs_count": len(refs),
            "summary": f"{project.name} 当前进入项目启动分析，重点是把资料缺口、历史技术复用和会议推进转成可执行任务。",
        },
        "technical_focus_cards": technical_focus_cards,
        "task_breakdown": task_breakdown,
        "meeting_agenda": meeting_agenda,
        "ppt_outline": ppt_outline,
        "risk_list": risk_list,
        "open_questions": open_questions,
        "mindmap_json": mindmap_json,
        "source_refs": refs + cross_project_refs,
        "cross_project_refs": cross_project_refs,
    }


def pending_analysis_files(project: models.Project) -> list[models.ProjectFile]:
    return [file for file in project.files if (file.analysis_status or "pending") == "pending"]


def _project_file_context(project: models.Project, limit: int = 8, files: Optional[list[models.ProjectFile]] = None) -> list[dict[str, str]]:
    contexts = []
    source_files = files if files is not None else project.files
    for file in source_files[:limit]:
        text = (file.parsed_text or "").strip()
        status = file.parse_status or "pending"
        if not text:
            text = "文件尚未解析出文本，请在分析中标记为资料未解析或仅可作为文件存在性参考。"
        contexts.append(
            {
                "file_id": file.id,
                "filename": file.filename,
                "filetype": file.filetype,
                "parse_status": status,
                "analysis_status": file.analysis_status or "pending",
                "text": text[:5000],
            }
        )
    return contexts


def build_startup_analysis_prompt(
    project: models.Project,
    chunks: list[models.KnowledgeChunk],
    files: Optional[list[models.ProjectFile]] = None,
    recent_meetings: Optional[list[models.Meeting]] = None,
    cross_project_refs: Optional[list[dict[str, Any]]] = None,
) -> str:
    file_context = _project_file_context(project, files=files)
    source_refs = _refs_from_chunks(chunks)
    cross_project_refs = cross_project_refs or []

    # 注入最近会议摘要用于跨会议综合
    meeting_context = []
    if recent_meetings:
        for m in recent_meetings[:3]:
            if m.summary:
                meeting_context.append(
                    {
                        "title": m.title,
                        "date": m.created_at.isoformat() if m.created_at else "",
                        "summary_excerpt": (m.summary or "")[:2000],
                    }
                )
    expected_schema = {
        "project_summary": {
            "name": "项目名称",
            "city": "城市",
            "project_type": "项目类型",
            "phase": "阶段",
            "description": "项目描述",
            "knowledge_refs_count": 0,
            "summary": "基于上传文件和知识库资料形成的真实启动分析摘要",
        },
        "technical_focus_cards": [
            {
                "title": "技术卡标题",
                "dimension": "日照/退界/面积/消防/规划/报批等维度",
                "summary": "结合上传文件的判断",
                "checkpoints": ["需要复核的具体事项"],
                "source_refs": ["引用的文件名或知识库来源"],
                "manual_confirm": "需要人工确认的内容或风险等级",
            }
        ],
        "task_breakdown": [
            {
                "task_name": "任务名称",
                "task_type": "任务类型",
                "priority": "高/中/低",
                "owner_role": "负责人角色",
                "estimated_days": 1,
                "dependencies": [],
                "risk_level": "高/中/低",
                "status": "todo",
                "output_requirement": "交付物要求",
            }
        ],
        "meeting_agenda": ["启动会要讨论的问题"],
        "ppt_outline": [{"page": 1, "title": "页面标题", "content": "页面核心内容"}],
        "risk_list": ["风险点"],
        "open_questions": ["待确认问题"],
        "mindmap_json": {"title": "项目启动分析", "nodes": []},
        "source_refs": [
            {
                "chunk_id": "来源ID",
                "source_file": "来源文件",
                "source_path": "来源路径",
                "heading": "标题",
                "quote": "引用片段",
                "relevance_score": 0.8,
            }
        ],
        "cross_project_refs": [
            {
                "source_file": "历史项目资料",
                "source_path": "来源路径",
                "quote": "可复用经验摘录",
                "hit_reason": "同城/同类型/关键词命中原因",
            }
        ],
    }
    meeting_section = ""
    if meeting_context:
        meeting_section = (
            "最近会议摘要（用于跨会议综合研判）：\n"
            f"{json.dumps(meeting_context, ensure_ascii=False, indent=2)}\n\n"
        )

    return (
        "请基于项目基本信息、用户上传并解析的文件内容、知识库检索片段以及最近会议摘要，生成建筑设计项目启动分析 JSON。\n"
        "必须优先分析上传文件里的真实内容；如果资料不足，请明确指出缺口，不要编造不存在的条件。\n"
        "只输出 JSON，不要输出 Markdown，不要解释。\n\n"
        "项目基本信息：\n"
        f"{json.dumps({'name': project.name, 'city': project.city, 'project_type': project.project_type, 'phase': project.phase, 'description': project.description}, ensure_ascii=False, indent=2)}\n\n"
        "本次待分析文件内容：\n"
        f"{json.dumps(file_context, ensure_ascii=False, indent=2)}\n\n"
        "知识库检索片段：\n"
        f"{json.dumps(source_refs, ensure_ascii=False, indent=2)}\n\n"
        "跨项目经验检索片段（所有业主偏好、周期、日照、退距等复用判断必须来自这里或上方来源；没有来源时写'未检索到可引用历史经验'）：\n"
        f"{json.dumps(cross_project_refs, ensure_ascii=False, indent=2)}\n\n"
        f"{meeting_section}"
        "输出 JSON Schema 示例：\n"
        f"{json.dumps(expected_schema, ensure_ascii=False, indent=2)}"
    )


def normalize_startup_analysis_payload(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload or {})
    for key in [
        "project_summary",
        "technical_focus_cards",
        "task_breakdown",
        "meeting_agenda",
        "ppt_outline",
        "risk_list",
        "open_questions",
        "mindmap_json",
        "source_refs",
        "cross_project_refs",
    ]:
        if not merged.get(key):
            merged[key] = fallback.get(key)
    if not isinstance(merged.get("project_summary"), dict):
        merged["project_summary"] = fallback.get("project_summary", {})
    if not isinstance(merged.get("mindmap_json"), dict):
        merged["mindmap_json"] = fallback.get("mindmap_json", {"title": "项目启动分析", "nodes": []})
    for key in ["technical_focus_cards", "task_breakdown", "meeting_agenda", "ppt_outline", "risk_list", "open_questions", "source_refs", "cross_project_refs"]:
        if not isinstance(merged.get(key), list):
            merged[key] = fallback.get(key, [])
    merged["mode"] = merged.get("mode") or "deepseek"
    return merged


def startup_analysis_to_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("project_summary", {})
    lines = [
        "# 项目启动分析",
        "",
        f"## 项目摘要",
        f"- 项目：{summary.get('name', '')}",
        f"- 阶段：{summary.get('phase', '')}",
        f"- 结论：{summary.get('summary', '')}",
        "",
        "## 技术重点",
    ]
    for card in payload.get("technical_focus_cards", []):
        lines.append(f"- **{card.get('dimension')}**：{card.get('summary')}")
    lines.extend(["", "## 任务拆解"])
    for task in payload.get("task_breakdown", []):
        lines.append(f"- {task.get('task_name')}（{task.get('owner_role')} / {task.get('priority')}）")
    lines.extend(["", "## 启动会议程"])
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(payload.get("meeting_agenda", []), start=1))
    lines.extend(["", "## PPT结构"])
    for item in payload.get("ppt_outline", []):
        lines.append(f"{item.get('page')}. {item.get('title')}：{item.get('content')}")
    lines.extend(["", "## 风险与未决问题"])
    lines.extend(f"- {item}" for item in payload.get("risk_list", []))
    lines.extend(f"- 待确认：{item}" for item in payload.get("open_questions", []))
    return "\n".join(lines)


def _upsert_startup_skill_card(
    db: Session,
    project: models.Project,
    card_type: str,
    title: str,
    markdown: str,
    output: dict[str, Any],
) -> models.SkillCard:
    card = db.scalar(
        select(models.SkillCard).where(models.SkillCard.project_id == project.id, models.SkillCard.card_type == card_type)
    )
    if not card:
        card = models.SkillCard(project_id=project.id, card_type=card_type)
        db.add(card)
    card.title = title
    card.status = "succeeded"
    card.input_data = safe_json_dump({"source": "startup_analysis"}, field_name="skill_card_input_data")
    card.output_data = safe_json_dump(output, field_name="skill_card_output_data")
    card.input_json = safe_json_dump({"source": "startup_analysis"}, field_name="skill_card_input_json")
    card.output_json = safe_json_dump(output, field_name="skill_card_output_json")
    card.markdown = markdown
    card.source = "startup_analysis"
    card.created_by = "system"
    card.completed_at = utc_now()
    return card


def _candidate_markdown(title: str, body: str, sources: list[str]) -> str:
    lines = [
        "---",
        "type: obsidian_candidate",
        f'title: "{title}"',
        "status: pending_review",
        f'updated: "{utc_now().date().isoformat()}",'
        "---",
        "",
        f"# {title}",
        "",
        body,
        "",
        "## 候选来源",
    ]
    lines.extend(f"- {source}" for source in sources[:8])
    return "\n".join(lines)


def save_startup_analysis(
    db: Session,
    project: models.Project,
    payload: dict[str, Any],
    analyzed_files: Optional[list[models.ProjectFile]] = None,
) -> models.ProjectReport:
    db.execute(
        delete(models.ProjectReport).where(
            models.ProjectReport.project_id == project.id,
            models.ProjectReport.report_type == "startup_analysis",
        )
    )
    db.execute(delete(models.KnowledgeReference).where(models.KnowledgeReference.project_id == project.id))
    report = models.ProjectReport(
        project_id=project.id,
        report_type="startup_analysis",
        content_json=safe_json_dump(payload, field_name="startup_content_json"),
        markdown=startup_analysis_to_markdown(payload),
        model_name=settings.deepseek_model if not settings.mock_mode else "mock",
        mode=payload.get("mode", "mock"),
    )
    db.add(report)
    for ref in payload.get("source_refs", [])[:12]:
        db.add(
            models.KnowledgeReference(
                project_id=project.id,
                source_file=ref.get("source_file", ""),
                source_path=ref.get("source_path", ""),
                chunk_id=ref.get("chunk_id", ""),
                quote=ref.get("quote", ""),
                relevance_score=float(ref.get("relevance_score") or 0),
            )
        )
    existing_task_names = {task.task_name for task in project.tasks}
    for item in payload.get("task_breakdown", []):
        if item["task_name"] in existing_task_names:
            continue
        db.add(
            models.ProjectTask(
                project_id=project.id,
                task_name=item["task_name"],
                task_type=item["task_type"],
                priority=item["priority"],
                owner_role=item["owner_role"],
                estimated_days=int(item["estimated_days"]),
                dependencies=safe_json_dump(item.get("dependencies", []), field_name="startup_task_dependencies"),
                risk_level=item["risk_level"],
                status=item["status"],
                output_requirement=item["output_requirement"],
            )
        )
    agenda_markdown = "# 项目启动会议程\n\n" + "\n".join(f"{idx}. {item}" for idx, item in enumerate(payload["meeting_agenda"], start=1))
    if not project.meetings:
        db.add(
            models.Meeting(
                project_id=project.id,
                title=f"{project.name} 项目启动会",
                agenda=agenda_markdown,
                status="scheduled",
                mindmap_json=safe_json_dump(payload["mindmap_json"], field_name="mindmap_json"),
                next_actions_json=safe_json_dump(payload["task_breakdown"], field_name="next_actions_json"),
            )
        )
    _upsert_startup_skill_card(
        db,
        project,
        "technical_focus",
        "技术重点卡",
        "## 技术重点\n" + "\n".join(f"- **{card['dimension']}**：{card['summary']}" for card in payload["technical_focus_cards"]),
        {"cards": payload["technical_focus_cards"]},
    )
    _upsert_startup_skill_card(
        db,
        project,
        "task_breakdown",
        "任务拆解卡",
        "## 启动任务\n" + "\n".join(f"- {task['task_name']}（{task['owner_role']}）" for task in payload["task_breakdown"]),
        {"items": payload["task_breakdown"]},
    )
    _upsert_startup_skill_card(
        db,
        project,
        "meeting_agenda",
        "会议议程卡",
        agenda_markdown,
        {"items": payload["meeting_agenda"]},
    )
    _upsert_startup_skill_card(
        db,
        project,
        "ppt_outline",
        "PPT结构卡",
        "## PPT结构\n" + "\n".join(f"{item['page']}. {item['title']}：{item['content']}" for item in payload["ppt_outline"]),
        {"slides": payload["ppt_outline"]},
    )
    sources = [ref.get("source_path", "") for ref in payload.get("source_refs", [])]
    db.execute(
        delete(models.KnowledgeItem).where(
            models.KnowledgeItem.project_id == project.id,
            models.KnowledgeItem.item_type == "obsidian_candidate",
        )
    )
    for card in payload.get("technical_focus_cards", []):
        db.add(
            models.KnowledgeItem(
                project_id=project.id,
                source_file=card["title"],
                item_type="obsidian_candidate",
                summary=card["summary"],
                tags=safe_json_dump(["技术卡", card["dimension"], "候选"], field_name="knowledge_item_tags"),
                content=_candidate_markdown(card["title"], card["summary"], sources),
            )
        )
    batch_id = uuid4().hex
    for file in analyzed_files or []:
        file.analysis_status = "analyzed"
        file.analysis_batch_id = batch_id
        file.analyzed_at = utc_now()
    db.flush()
    deposit_startup_analysis_to_knowledge(db, project, payload, report.id)
    db.commit()
    db.refresh(report)
    return report


async def run_startup_analysis(db: Session, project: models.Project) -> dict[str, Any]:
    question = " ".join(
        [
            project.name,
            project.city,
            project.project_type,
            project.phase,
            project.description,
            "日照 退界 面积计算 消防 规划条件 报批 强排 会议纪要",
        ]
    )
    chunks = search_knowledge(db, question, limit=10)
    cross_project_refs = collect_cross_project_experience(db, project, limit=6)
    analysis_files = pending_analysis_files(project)
    recent_meetings = sorted(project.meetings, key=lambda m: m.created_at, reverse=True)[:3] if project.meetings else []
    fallback_payload = build_startup_analysis_payload(project, chunks, cross_project_refs=cross_project_refs)
    if analysis_files:
        fallback_payload["analysis_scope"] = {
            "mode": "pending_files_only",
            "file_count": len(analysis_files),
            "filenames": [file.filename for file in analysis_files],
        }
    payload = fallback_payload
    if not settings.mock_mode:
        try:
            deepseek_payload = await call_deepseek_json(
                build_startup_analysis_prompt(
                    project,
                    chunks,
                    files=analysis_files,
                    recent_meetings=recent_meetings,
                    cross_project_refs=cross_project_refs,
                )
            )
            if deepseek_payload:
                payload = normalize_startup_analysis_payload(deepseek_payload, fallback_payload)
                payload["mode"] = "deepseek"
            else:
                raise RuntimeError("DeepSeek 未返回有效结构化分析")
        except Exception as exc:
            raise RuntimeError(f"DeepSeek 真实分析失败：{exc}") from exc
    report = save_startup_analysis(db, project, payload, analyzed_files=analysis_files)
    # 变更事件：启动分析完成
    from .event_engine import emit_change_event
    emit_change_event(
        db, project.id, "startup_analysis_generated",
        source_type="system", source_id=str(report.id),
        description="启动分析完成",
    )
    return {"report": report, **payload}


# ──────────────────────────── 增量分析 ────────────────────────────


def build_incremental_analysis_prompt(
    project: models.Project,
    last_report: models.ProjectReport,
    unconsumed_events: list,
    recent_meetings: list = None,
    new_files: list = None,
) -> str:
    """构建增量分析 prompt - 只关注自上次分析后的变化"""

    # 上次分析摘要（截取前 3000 字）
    last_summary = (last_report.markdown or "")[:3000]

    # 格式化变更事件
    event_lines = []
    for e in unconsumed_events:
        desc = e.description or e.event_type
        event_lines.append(f"- [{e.event_type}] {desc}")
    events_text = "\n".join(event_lines) if event_lines else "无新变更"

    # 新会议摘要
    meeting_text = ""
    if recent_meetings:
        meeting_parts = []
        for m in recent_meetings[:5]:
            if m.summary:
                meeting_parts.append(f"### {m.title or '未命名会议'}\n{(m.summary or '')[:1500]}")
        meeting_text = "\n\n".join(meeting_parts)

    # 新文件内容
    file_text = ""
    if new_files:
        file_parts = []
        for f in new_files[:5]:
            if f.parsed_text:
                file_parts.append(f"### {f.filename}\n{(f.parsed_text or '')[:1000]}")
        file_text = "\n\n".join(file_parts)

    prompt = f"你是建筑设计项目的增量分析助手。项目名称：{project.name or '未命名'}。"
    prompt += "\n严格输出 JSON，不要输出任何额外文字。"
    prompt += "只基于提供的变更事件和新内容进行分析，不要编造信息。"
    prompt += f"""

## 上次分析报告摘要（截止到上次分析时）

{last_summary}

## 自上次分析以来的变更事件

{events_text}

## 新增会议纪要

{meeting_text if meeting_text else '无新会议'}

## 新增文件内容

{file_text if file_text else '无新文件'}

---

请基于以上变更，输出增量更新建议。严格输出 JSON，字段如下：

{{{{
  "has_significant_change": true/false,
  "change_summary": "一句话概述本次变更的核心影响",
  "delta_technical_focus": [
    {{"action": "add/modify/remove", "item": "具体技术重点", "reason": "原因"}}
  ],
  "delta_tasks": [
    {{"action": "add/reprioritize/remove", "task_name": "任务名", "priority": "high/medium/low", "reason": "原因"}}
  ],
  "delta_risks": [
    {{"action": "add/resolve", "risk": "风险描述", "reason": "原因"}}
  ],
  "resolved_questions": [
    {{"question": "之前的开放问题", "answer": "本次会议/文件中的解答"}}
  ],
  "okf_update_suggestions": [
    "建议更新的 OKF 字段或技能卡类型"
  ]
}}}}

规则：
1. 如果变更微小且不影响项目方向，has_significant_change 设为 false，其他数组留空
2. delta_tasks 中 reprioritize 表示优先级调整，不是新增
3. resolved_questions 只填确实在新内容中找到答案的问题
4. 不要编造不存在的变更，严格基于提供的事件和内容"""

    return prompt


async def run_incremental_analysis(project_id: str, db) -> dict:
    """执行增量分析 - 只分析未消费的变更"""
    from .event_engine import get_unconsumed_events, mark_events_consumed

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise ValueError(f"项目不存在: {project_id}")

    # 1. 获取上一次分析报告
    last_report = (
        db.query(models.ProjectReport)
        .filter(
            models.ProjectReport.project_id == project_id,
            models.ProjectReport.report_type == "project_analysis",
        )
        .order_by(models.ProjectReport.created_at.desc())
        .first()
    )

    if not last_report:
        return {"status": "no_previous_analysis", "message": "尚无历史分析报告，请先执行启动分析"}

    # 2. 获取未消费事件
    unconsumed = get_unconsumed_events(db, project_id)
    if not unconsumed:
        return {"status": "no_change_detected", "message": "无新变更，分析仍然有效"}

    # 3. 获取新会议（自上次分析后）
    recent_meetings = (
        db.query(models.Meeting)
        .filter(
            models.Meeting.project_id == project_id,
            models.Meeting.created_at > last_report.created_at,
        )
        .order_by(models.Meeting.created_at.desc())
        .limit(5)
        .all()
    )

    # 4. 获取新文件（自上次分析后）
    new_files = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.project_id == project_id,
            models.ProjectFile.created_at > last_report.created_at,
            models.ProjectFile.parse_status == "parsed",
        )
        .limit(5)
        .all()
    )

    # 5. 构建 prompt
    prompt = build_incremental_analysis_prompt(
        project, last_report, unconsumed, recent_meetings, new_files
    )

    # 6. 调用 DeepSeek（call_deepseek_json 只接受 prompt 参数，系统指令已嵌入 prompt）
    if settings.mock_mode:
        result_json = _mock_incremental_result()
    else:
        result_json = await call_deepseek_json(prompt)

    if not result_json:
        return {"status": "analysis_failed", "message": "AI 分析返回为空"}

    # 7. 生成 diff_summary markdown
    diff_md = _format_incremental_diff(result_json)

    # 8. 保存为新的 ProjectReport
    new_report = models.ProjectReport(
        id=uuid4().hex,
        project_id=project_id,
        report_type="project_analysis",
        content_json=safe_json_dump(result_json, field_name="incremental_content_json"),
        markdown=diff_md,
        mode="deepseek" if not settings.mock_mode else "mock",
        model_name=settings.deepseek_model if not settings.mock_mode else "mock",
        parent_report_id=last_report.id,
        diff_summary=result_json.get("change_summary", ""),
    )
    db.add(new_report)

    # 9. 标记事件已消费
    event_ids = [e.id for e in unconsumed]
    mark_events_consumed(db, event_ids)

    # 10. 应用增量变更（可选：更新 risk_summary）
    delta_risks = result_json.get("delta_risks", [])
    if delta_risks:
        existing_risks = safe_json_parse(project.risk_summary, default=[], field_name="risk_summary") if project.risk_summary else []
        if not isinstance(existing_risks, list):
            existing_risks = []
        for dr in delta_risks:
            if isinstance(dr, dict) and dr.get("action") == "add":
                risk_text = dr.get("risk", "")
                if risk_text and risk_text not in existing_risks:
                    existing_risks.append(risk_text)
        project.risk_summary = safe_json_dump(existing_risks, field_name="risk_summary")

    db.commit()

    return {
        "status": "completed",
        "has_significant_change": result_json.get("has_significant_change", False),
        "change_summary": result_json.get("change_summary", ""),
        "diff_summary": diff_md,
        "events_consumed": len(event_ids),
        "report_id": new_report.id,
    }


def _mock_incremental_result() -> dict:
    """Mock 增量分析结果"""
    return {
        "has_significant_change": True,
        "change_summary": "甲方在最近会议中提出立面品质提升和入口仪式感要求，需调整设计重点",
        "delta_technical_focus": [
            {"action": "add", "item": "立面材料质感提升方案", "reason": "甲方明确提出'不够高级'"},
            {"action": "modify", "item": "入口设计", "reason": "新增仪式感要求"},
        ],
        "delta_tasks": [
            {"action": "add", "task_name": "立面材料方案比选", "priority": "high", "reason": "甲方核心诉求"},
            {"action": "reprioritize", "task_name": "景观深化", "priority": "medium", "reason": "优先处理立面"},
        ],
        "delta_risks": [
            {"action": "add", "risk": "立面造价可能超预算", "reason": "品质提升必然带来成本压力"},
        ],
        "resolved_questions": [
            {"question": "甲方对立面风格的具体偏好", "answer": "偏好石材+金属组合，要求高级感"},
        ],
        "okf_update_suggestions": ["technical_focus", "task_breakdown"],
    }


def _format_incremental_diff(result: dict) -> str:
    """将增量分析结果格式化为 Markdown"""
    lines = ["# 增量分析报告\n"]

    summary = result.get("change_summary", "")
    if summary:
        lines.append(f"**变更摘要**：{summary}\n")

    # 技术重点变化
    delta_focus = result.get("delta_technical_focus", [])
    if delta_focus:
        lines.append("\n## 技术重点变化\n")
        for item in delta_focus:
            if isinstance(item, dict):
                action = item.get("action", "")
                text = item.get("item", "")
                reason = item.get("reason", "")
                emoji = {"add": "➕", "modify": "✏️", "remove": "❌"}.get(action, "•")
                lines.append(f"- {emoji} {text}（{reason}）")

    # 任务变化
    delta_tasks = result.get("delta_tasks", [])
    if delta_tasks:
        lines.append("\n## 任务调整\n")
        for item in delta_tasks:
            if isinstance(item, dict):
                action = item.get("action", "")
                name = item.get("task_name", "")
                priority = item.get("priority", "")
                reason = item.get("reason", "")
                emoji = {"add": "➕", "reprioritize": "🔄", "remove": "❌"}.get(action, "•")
                lines.append(f"- {emoji} {name} [{priority}]（{reason}）")

    # 风险变化
    delta_risks = result.get("delta_risks", [])
    if delta_risks:
        lines.append("\n## 风险更新\n")
        for item in delta_risks:
            if isinstance(item, dict):
                action = item.get("action", "")
                risk = item.get("risk", "")
                emoji = {"add": "⚠️", "resolve": "✅"}.get(action, "•")
                lines.append(f"- {emoji} {risk}")

    # 已解答问题
    resolved = result.get("resolved_questions", [])
    if resolved:
        lines.append("\n## 已解答的开放问题\n")
        for item in resolved:
            if isinstance(item, dict):
                q = item.get("question", "")
                a = item.get("answer", "")
                lines.append(f"- **Q**: {q}")
                lines.append(f"  **A**: {a}")

    return "\n".join(lines)
