"""execution.py — 项目执行、Agent Chat、Skill Card、会议总结"""
import base64
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.json_safety import safe_json_dump, safe_json_parse
from app.utils import utc_now
from app.skill_manifest import SKILL_BY_ID, SkillDefinition, list_builtin_skills, match_skill_by_keywords
from app.services.knowledge import search_knowledge, _refs_from_chunks
from app.services.context import deposit_meeting_transcript_to_knowledge, deposit_meeting_summary_to_knowledge
from app.services.analysis import call_deepseek_json, call_deepseek_text
from app.services.core import project_upload_dir
from app.services.image_prompting import build_multiview_image_prompts


# ──────────────────────────── 项目执行 ────────────────────────────

def classify_project_execution_instruction(project: models.Project, instruction: str) -> str:
    text = instruction.strip().lower()
    compact = re.sub(r"[\s，。！？!?,.、~～]+", "", text)
    if compact in {"你好", "您好", "hello", "hi", "嗨", "哈喽", "在吗", "在不在"}:
        return "greeting"

    project_terms = {
        project.name,
        project.city,
        project.project_type,
        project.phase,
        "项目",
        "资料",
        "任务",
        "会议",
        "纪要",
        "执行",
        "设计",
        "方案",
        "强排",
        "总图",
        "日照",
        "退界",
        "消防",
        "面积",
        "容积率",
        "报批",
        "规划",
        "楼栋",
        "户型",
        "配套",
        "风险",
        "知识库",
    }
    if any(term and str(term).lower() in text for term in project_terms):
        return "project"
    return "unrelated"


def build_project_execution_greeting(project: models.Project) -> str:
    return "你好，我在。你可以直接问我和\u201c" + project.name + "\u201d有关的问题，我会按当前项目资料、任务、会议纪要和知识库来回答。"


def build_project_execution_refusal(project: models.Project) -> str:
    return "这个问题和当前项目\u201c" + project.name + "\u201d没有直接关系，我先不展开回答。请发和项目资料、任务、会议、设计风险或推进安排有关的问题。"


def build_project_execution_prompt(project: models.Project, instruction: str, chunks: list[models.KnowledgeChunk]) -> str:
    latest_report = next((report for report in sorted(project.reports, key=lambda item: item.created_at, reverse=True)), None)
    context = {
        "project": {
            "name": project.name,
            "city": project.city,
            "project_type": project.project_type,
            "phase": project.phase,
            "description": project.description,
            "status": project.status,
        },
        "latest_report": (latest_report.markdown[:3000] if latest_report and latest_report.markdown else ""),
        "tasks": [
            {
                "task_name": task.task_name,
                "owner_role": task.owner_role,
                "priority": task.priority,
                "risk_level": task.risk_level,
                "status": task.status,
                "output_requirement": task.output_requirement,
            }
            for task in project.tasks[:20]
        ],
        "meetings": [
            {
                "title": meeting.title,
                "agenda": (meeting.agenda or "")[:800],
                "summary": (meeting.summary or "")[:1200],
                "status": meeting.status,
            }
            for meeting in project.meetings[:8]
        ],
        "knowledge_references": [
            {
                "source_file": ref.source_file,
                "source_path": ref.source_path,
                "quote": ref.quote[:500],
            }
            for ref in project.knowledge_references[:10]
        ],
        "retrieved_knowledge": [
            {
                "path": chunk.path,
                "heading": chunk.heading,
                "content": chunk.content[:900],
            }
            for chunk in chunks
        ],
    }
    return (
        "你是建筑设计项目执行助手。请基于项目上下文、本地知识库检索结果和用户指令执行工作。\n"
        "要求：\n"
        "1. 直接回应用户发来的具体问题，不要套固定项目模板，不要答非所问。\n"
        "2. 必须优先使用项目上下文和知识库内容，不要编造来源。\n"
        "3. 如果用户问题与当前项目无关，只能礼貌说明无法在项目执行台回答无关内容。\n"
        "4. 普通打招呼可以自然回应，不要强行输出项目分析。\n"
        "5. 输出要服务项目推进；只有在用户问题需要时，才包含判断、拆解、风险和下一步建议。\n"
        "6. 如果适合转成任务，请列出任务名、负责人角色、优先级和交付物。\n"
        "7. 如使用了知识库内容，可以在答案末尾简短列出来源路径；没有使用来源时不要写引用或来源说明。\n\n"
        f"用户指令：{instruction}\n\n"
        "项目执行上下文：\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


async def run_project_execution(db: Session, project: models.Project, instruction: str) -> models.AgentRun:
    instruction_type = classify_project_execution_instruction(project, instruction)
    chunks: list[models.KnowledgeChunk] = []
    prompt = ""
    if instruction_type == "greeting":
        mode = "greeting"
        answer = build_project_execution_greeting(project)
    elif instruction_type == "unrelated":
        mode = "refused"
        answer = build_project_execution_refusal(project)
    else:
        query = " ".join([project.name, project.city, project.project_type, project.phase, instruction])
        chunks = search_knowledge(db, query, limit=8)
        prompt = build_project_execution_prompt(project, instruction, chunks)
        mode = "mock" if settings.mock_mode else "deepseek"
        try:
            if settings.mock_mode:
                answer = (
                    f"『Mock模式』已读取 {project.name} 的项目上下文，并检索到 {len(chunks)} 条知识库片段。\n\n"
                    "针对\u201c" + instruction + "\u201d，建议先围绕资料缺口、技术风险、任务责任人和交付物四类事项拆解。\n\n"
                    "## 下一步建议\n"
                    "- 明确本轮要解决的关键技术问题。\n"
                    "- 对照知识库历史项目经验形成复核清单。\n"
                    "- 将结论转为任务或沉淀为项目知识。"
                )
            else:
                answer = await call_deepseek_text(
                    prompt=prompt,
                    system_prompt="你是建筑设计项目执行助手。只基于用户当前问题、项目上下文和本地知识库回答；无关内容礼貌拒绝；普通问候自然回应；输出中文 Markdown。",
                )
        except Exception as exc:
            mode = "deepseek_error"
            answer = (
                "DeepSeek 调用失败，已回退为本地执行摘要。\n\n"
                f"- 指令：{instruction}\n"
                f"- 已检索知识片段：{len(chunks)} 条\n"
                f"- 错误类型：{exc.__class__.__name__}\n\n"
                "建议稍后重试，或先基于当前项目任务和会议纪要手动推进。"
            )
    output = {
        "mode": mode,
        "answer": answer,
        "references": [
            {
                "chunk_id": chunk.id,
                "source_path": chunk.path,
                "heading": chunk.heading,
                "quote": chunk.content[:420],
            }
            for chunk in chunks
        ],
    }
    run = models.AgentRun(
        project_id=project.id,
        agent_id="project-execution",
        input_context=json.dumps({"instruction": instruction, "instruction_type": instruction_type, "prompt": prompt}, ensure_ascii=False),
        output_json=json.dumps(output, ensure_ascii=False),
        status="succeeded" if mode != "deepseek_error" else "failed",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# ──────────────────────────── 团队计划 ────────────────────────────

def build_team_plan(db: Session, project: models.Project) -> models.TeamPlan:
    employees = list(db.scalars(select(models.DigitalEmployee)))
    tasks = project.tasks
    role_tasks: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        role_tasks[task.owner_role or "AI项目经理"].append(task.task_name)
    roles = []
    for employee in employees:
        matched = role_tasks.get(employee.name) or role_tasks.get(employee.role) or []
        if matched or employee.name in {"AI项目经理", "AI资料管理员", "AI汇报助理"}:
            roles.append(
                {
                    "name": employee.name,
                    "role": employee.role,
                    "recommended_count": 1,
                    "tasks": matched[:6],
                    "skills": safe_json_parse(employee.skills, default=[], field_name="employee_skills"),
                    "intensity": "高" if matched else "中",
                    "risk_note": "需要人工确认任务边界和交付标准。",
                }
            )
    if not roles:
        roles = [
            {
                "name": "AI项目经理",
                "role": "项目负责人 / PM",
                "recommended_count": 1,
                "tasks": [],
                "skills": ["任务拆解"],
                "intensity": "中",
                "risk_note": "Mock 规则生成。",
            }
        ]
    plan = models.TeamPlan(
        project_id=project.id,
        recommended_roles=json.dumps(roles, ensure_ascii=False),
        staffing_summary=f"建议 {len(roles)} 类数字员工参与；需要根据真实任务继续校准投入强度。",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# ──────────────────────────── 会议总结 ────────────────────────────

def default_meeting_agenda(project: models.Project) -> str:
    return "\n".join(
        [
            f"# {project.name} 项目启动会议程",
            "1. 确认项目背景、业主诉求与当前设计阶段。",
            "2. 核对规划条件、红线、日照、退界、面积计算等技术资料缺口。",
            "3. 复盘历史相似项目可复用经验和风险清单。",
            "4. 明确本轮交付物、节点时间和责任人。",
            "5. 确认下一次业主沟通需要决策的问题。",
        ]
    )


def _format_meeting_summary_markdown(project_name: str, payload: dict[str, Any]) -> str:
    summary = str(payload.get("summary") or "").strip()
    core_items = [str(item).strip() for item in payload.get("core_items", []) if str(item).strip()]
    demand_translation = payload.get("demand_translation", []) or []
    decisions = [str(item).strip() for item in payload.get("decisions", []) if str(item).strip()]
    risks = [str(item).strip() for item in payload.get("risks", []) if str(item).strip()]
    next_steps = [str(item).strip() for item in payload.get("next_steps", []) if str(item).strip()]
    broadcast_script = str(payload.get("broadcast_script") or "").strip()
    lines = [f"# {project_name} 五段式会议纪要", "", "## 1. 纪要内容", summary or "未能从真实转写中提取明确摘要。"]
    if core_items:
        lines.extend(["", "## 2. 核心事项", *[f"- {item}" for item in core_items]])
    if demand_translation:
        lines.extend(["", "## 3. 甲方诉求转译（内部研判）"])
        for item in demand_translation:
            if isinstance(item, dict):
                raw = str(item.get("raw") or item.get("source") or "原话待确认").strip()
                time = str(item.get("time") or "时间点待确认").strip()
                translation = str(item.get("translation") or item.get("meaning") or "转译待复核").strip()
                action = str(item.get("design_response") or item.get("action") or "").strip()
                lines.append(f"- 原话：{raw}（{time}）")
                lines.append(f"  转译：{translation}")
                if action:
                    lines.append(f"  设计回应：{action}")
                confidence = str(item.get("confidence") or "").strip()
                category = str(item.get("category") or "").strip()
                meta_parts = []
                if confidence:
                    meta_parts.append(f"置信度：{confidence}")
                if category:
                    meta_parts.append(f"类别：{category}")
                if meta_parts:
                    lines.append(f"  {'｜'.join(meta_parts)}")
            else:
                lines.append(f"- {item}")
    if decisions:
        lines.extend(["", "## 4. 会议决议", *[f"- {item}" for item in decisions]])
    if risks:
        lines.extend(["", "## 风险与问题", *[f"- {item}" for item in risks]])
    if next_steps:
        lines.extend(["", "## 5. 待办事项", *[f"- {item}" for item in next_steps]])
    if broadcast_script:
        lines.extend(["", "## 语音播报稿", broadcast_script])
    return "\n".join(lines).strip()


def _fallback_real_transcript_summary(project_name: str, transcript: str) -> tuple[str, list[dict[str, str]]]:
    excerpt = transcript.strip()[:1800]
    summary = (
        f"# {project_name} 会议纪要\n\n"
        "## 摘要\n"
        "以下内容基于腾讯会议真实转写生成。当前模型未返回结构化纪要，先保留原始转写摘要供复核。\n\n"
        "## 原始转写摘录\n"
        f"{excerpt}"
    )
    return summary, []


async def summarize_meeting(db: Session, meeting: models.Meeting) -> models.Meeting:
    project = db.get(models.Project, meeting.project_id)
    project_name = project.name if project else "当前项目"
    transcript = (meeting.transcript or "").strip()
    if not transcript:
        raise ValueError("请先同步腾讯会议真实转写，再生成AI纪要")

    # 从知识库检索甲方黑话词典
    dict_chunks = []
    try:
        dict_chunks = search_knowledge(db, "甲方黑话词典 诉求转译", limit=3)
    except Exception:
        pass
    dict_content = "\n".join(chunk.content for chunk in dict_chunks if chunk.content) if dict_chunks else ""

    dict_instruction = ""
    if dict_content:
        dict_instruction = f"甲方诉求转译词典（来自知识库，优先使用）：\n{dict_content}\n词典未覆盖的新说法按相似逻辑自行转译并标注 confidence: medium。\n\n"
    else:
        dict_instruction = "甲方诉求转译参考：将甲方模糊/感性表达转译为设计专业语言，例如'不够高级'→材料质感/比例/留白/入口仪式感等。\n\n"

    prompt = (
        "请只基于以下真实转写（腾讯同步或手动粘贴）生成五段式会议纪要，不要补充转写中没有的信息。\n"
        "输出 JSON，字段：summary 字符串；core_items 字符串数组；"
        "demand_translation 数组，每项包含 raw、time、translation、design_response、"
        "confidence(high/medium/low，high=词典精确命中，medium=部分命中或自行推理，low=无法判断建议复核)、"
        "category(品质/风格/节奏/成本/进度/功能 之一)，"
        "仅转译真实出现的甲方模糊诉求，例如『不够高级/没气势/不像某风格』；"
        "decisions 字符串数组；risks 字符串数组；next_steps 字符串数组；"
        "todos 数组，每项包含 title、owner、status；broadcast_script 字符串。"
        "如果无法判断负责人，owner 写『待确认』；status 默认 todo。\n\n"
        f"{dict_instruction}"
        f"项目：{project_name}\n"
        f"会议标题：{meeting.title}\n"
        f"真实转写：\n{transcript[:12000]}"
    )
    actions: list[dict[str, str]] = []
    try:
        payload = await call_deepseek_json(prompt)
    except Exception:
        payload = {}
    if payload:
        meeting.summary = _format_meeting_summary_markdown(project_name, payload)
        for item in payload.get("todos", []):
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                if title:
                    actions.append(
                        {
                            "title": title,
                            "owner": str(item.get("owner") or "待确认").strip() or "待确认",
                            "status": str(item.get("status") or "todo").strip() or "todo",
                        }
                    )
    else:
        meeting.summary, actions = _fallback_real_transcript_summary(project_name, transcript)

    meeting.mindmap_json = "{}"
    meeting.next_actions_json = safe_json_dump(actions, field_name="next_actions_json")
    meeting.status = "summarized"
    if project:
        deposit_meeting_transcript_to_knowledge(db, project, meeting)
        deposit_meeting_summary_to_knowledge(db, project, meeting)
    db.commit()

    if project:
        for item in actions:
            existing = db.scalar(
                select(models.ProjectTask).where(
                    models.ProjectTask.project_id == project.id,
                    models.ProjectTask.source_type == "meeting",
                    models.ProjectTask.source_id == meeting.id,
                    models.ProjectTask.task_name == item["title"],
                )
            )
            if existing:
                continue
            db.add(
                models.ProjectTask(
                    project_id=project.id,
                    task_name=item["title"],
                    task_type="会议待办",
                    priority="高",
                    owner_role=item["owner"],
                    estimated_days=2,
                    dependencies="[]",
                    risk_level="中",
                    status="todo",
                    output_requirement="来自会议纪要自动生成，需要项目经理确认。",
                    source_type="meeting",
                    source_id=meeting.id,
                )
            )
        db.commit()
    db.refresh(meeting)
    return meeting


# ──────────────────────────── Skill Card ────────────────────────────

def _project_context_pack(project: models.Project) -> dict[str, Any]:
    files = list(project.files[:12])
    meetings = list(project.meetings[:6])
    tasks = list(project.tasks[:10])
    reports = list(project.reports[:4])
    refs = list(project.knowledge_references[:8])
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "city": project.city,
            "type": project.project_type,
            "phase": project.phase,
            "status": project.status,
            "description": project.description,
        },
        "files": [
            {
                "name": file.filename,
                "type": file.filetype,
                "parse_status": file.parse_status,
                "summary": (file.parsed_text or "")[:600],
            }
            for file in files
        ],
        "meetings": [
            {
                "title": meeting.title,
                "summary": (meeting.summary or "")[:800],
                "next_actions": meeting.next_actions_json,
            }
            for meeting in meetings
        ],
        "tasks": [
            {
                "name": task.task_name,
                "status": task.status,
                "priority": task.priority,
                "risk": task.risk_level,
                "owner": task.owner_role,
            }
            for task in tasks
        ],
        "reports": [
            {
                "type": report.report_type,
                "markdown": (report.markdown or "")[:1200],
            }
            for report in reports
        ],
        "knowledge_references": [
            {
                "source": ref.source_file,
                "quote": ref.quote,
                "score": ref.relevance_score,
            }
            for ref in refs
        ],
        "counts": {
            "files": len(project.files),
            "meetings": len(project.meetings),
            "tasks": len(project.tasks),
            "knowledge_refs": len(project.knowledge_references),
            "skill_cards": len(project.skill_cards),
        },
    }


def _skill_source_refs(chunks: list[models.KnowledgeChunk], project: models.Project) -> list[dict[str, str]]:
    refs = _refs_from_chunks(chunks) if chunks else []
    if refs:
        return [
            {
                "source_file": str(ref.get("source_file") or ref.get("source_path") or "知识库"),
                "quote": str(ref.get("quote") or "")[:240],
            }
            for ref in refs
        ]
    return [
        {"source_file": ref.source_file, "quote": (ref.quote or "")[:240]}
        for ref in project.knowledge_references[:6]
    ]


def _fallback_skill_output(skill: SkillDefinition, project: models.Project, prompt: str, sources: list[dict[str, str]]) -> dict[str, Any]:
    project_name = project.name or "当前项目"
    common_sources = sources or [{"source_file": "当前项目上下文", "quote": "尚未检索到明确知识库来源。"}]
    if skill.id == "brief_interpretation":
        return {
            "explicit_goals": ["确认项目任务书中的建设目标、阶段成果和汇报对象"],
            "implicit_goals": ["补齐甲方真实诉求、审查设计矛盾与边界条件"],
            "design_conflicts": ["资料完整性与方案判断之间仍有缺口"],
            "entry_points": ["先完成资料归档与任务书解读，再形成汇报主线"],
            "sources": common_sources,
        }
    if skill.id == "task_breakdown":
        return {
            "tasks": [
                {"title": "补齐项目基础资料", "owner": "项目经理", "priority": "高", "deliverable": "资料缺口清单"},
                {"title": "复核技术边界", "owner": "技术负责人", "priority": "高", "deliverable": "日照/退界/指标风险表"},
                {"title": "搭建汇报结构", "owner": "方案主创", "priority": "中", "deliverable": "PPT大纲"},
            ],
            "next": "可将任务写回任务看板后分派。",
        }
    if skill.id == "technical_focus":
        return {
            "cards": [
                {"dimension": "日照", "risk": "中", "checkpoints": ["日照标准", "遮挡关系", "测算口径"]},
                {"dimension": "退界", "risk": "中", "checkpoints": ["红线", "绿线", "消防登高面"]},
                {"dimension": "面积", "risk": "中", "checkpoints": ["容积率", "计容口径", "地库边界"]},
                {"dimension": "消防", "risk": "高", "checkpoints": ["消防车道", "登高场地", "防火分区"]},
            ],
            "sources": common_sources,
        }
    if skill.id == "meeting_minutes":
        return {
            "summary": f"{project_name} 本次会议围绕项目推进、资料补齐和下一步成果进行讨论。",
            "core_items": ["确认下一阶段汇报目标", "补齐技术边界资料", "形成可执行待办"],
            "demand_translation": [
                {
                    "raw": prompt[:160] or "待补充会议原话",
                    "time": "待确认",
                    "translation": "需要转化为材料、比例、界面、体量或汇报逻辑上的明确设计动作。",
                    "internal_only": True,
                }
            ],
            "decisions": ["先完成资料归档与技术边界复核，再进入汇报结构深化。"],
            "todos": [{"title": "整理会议待办并分配责任人", "owner": "项目经理", "status": "todo"}],
            "broadcast_script": "本次会议确认了资料补齐、技术边界复核和下一步汇报准备三项重点，请项目团队优先处理。",
            "sources": common_sources,
        }
    if skill.id == "ppt_outline":
        return {
            "title": f"{project_name} 方案汇报框架",
            "slides": [
                {"page": 1, "title": "封面", "content": "项目名称、阶段、汇报对象"},
                {"page": 2, "title": "项目背景", "content": "城市、区位、用地与甲方目标"},
                {"page": 3, "title": "核心问题", "content": "设计矛盾、技术边界、风险点"},
                {"page": 4, "title": "设计主线", "content": "概念、空间策略、产品策略"},
                {"page": 5, "title": "方案展开", "content": "总图、流线、户型/功能、立面方向"},
                {"page": 6, "title": "下一步", "content": "待补资料、关键节点与责任分工"},
            ],
            "key_messages": ["结论前置", "风险透明", "策略可执行"],
            "missing_assets": ["关键图纸", "技术指标", "参考案例"],
            "sources": common_sources,
        }
    if skill.id == "concept_copy":
        return {
            "concept_title": f"{project_name} 的场景更新与秩序重构",
            "narrative": "从场地真实约束和甲方诉求出发，建立清晰的空间秩序、识别性界面与可落地的产品表达。",
            "strategies": ["强化入口界面", "控制体量比例", "建立连续公共空间", "让材料与尺度回应项目定位"],
            "presentation_copy": "本方案以清晰的空间秩序回应场地约束，以克制而有识别度的建筑表达建立项目记忆点。",
            "sources": common_sources,
        }
    if skill.id == "competitor_analysis":
        return {
            "comparables": ["历史项目/案例库待检索后自动回填"],
            "transferable_strategies": ["入口仪式感", "材料层级", "展示界面", "汇报叙事结构"],
            "limits": ["不同城市、甲方、容积率与报批环境下不可直接套用。"],
            "risks": ["若缺少真实历史项目索引，竞品分析会退化为方法建议。"],
            "sources": common_sources,
        }
    if skill.id == "reference_image_classification":
        return {
            "image_type": "待分类参考图",
            "style_tags": ["现代", "克制", "展示面"],
            "material_tags": ["石材", "金属", "玻璃"],
            "reuse_points": ["入口界面", "立面比例", "材料层级"],
            "next_prompt": "可继续生成基于当前项目的生图提示词。",
        }
    if skill.id == "image_prompt":
        return {
            "positive_prompt": f"{project_name}，建筑方案前期意向图，结合城市语境、项目阶段与甲方诉求，现代克制，高品质材料，清晰体量比例，真实建筑摄影感",
            "negative_prompt": "低清晰度，过度奇幻，结构不合理，文字水印，畸形透视",
            "style_tags": ["建筑摄影", "方案意向", "高品质", "克制"],
            "camera": "eye-level architectural photography, 35mm lens",
            "usage": "用于方案前期风格探索与汇报意向沟通",
            "sources": common_sources,
        }
    if skill.id == "scheme_review":
        return {
            "strengths": ["项目已有资料可支撑基础判断"],
            "risks": ["技术边界、甲方诉求和成果缺口仍需复核"],
            "missing_info": ["完整任务书", "最新会议结论", "指标表", "关键图纸"],
            "next_actions": ["先补齐资料，再做方案评审定稿"],
            "sources": common_sources,
        }
    return {"result": "已生成基础成果。", "sources": common_sources}


def _markdown_from_output(skill: SkillDefinition, output: dict[str, Any], prompt: str) -> str:
    lines = [f"# {skill.name}", ""]
    if prompt:
        lines.extend(["## 用户需求", prompt, ""])
    for key, value in output.items():
        title = {
            "summary": "纪要内容",
            "core_items": "核心事项",
            "demand_translation": "甲方诉求转译",
            "decisions": "会议决议",
            "todos": "待办事项",
            "broadcast_script": "播报稿",
            "slides": "PPT框架",
            "tasks": "任务清单",
            "sources": "来源",
        }.get(key, key)
        lines.append(f"## {title}")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    lines.append("- " + "；".join(f"{k}: {v}" for k, v in item.items() if k != "sources"))
                else:
                    lines.append(f"- {item}")
        elif isinstance(value, dict):
            for item_key, item_value in value.items():
                lines.append(f"- {item_key}: {item_value}")
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines).strip()


def _normalize_skill_id(card_type: str) -> str:
    aliases = {
        "ppt_structure": "ppt_outline",
        "tech_points": "technical_focus",
        "image_generation": "ai_image_generation",
        "ai_image": "ai_image_generation",
    }
    return aliases.get(card_type, card_type)


async def _deepseek_skill_output(skill: SkillDefinition, project: models.Project, prompt: str, context: dict[str, Any], sources: list[dict[str, str]]) -> dict[str, Any]:
    if settings.mock_mode:
        return _fallback_skill_output(skill, project, prompt, sources)
    schema_hint = "、".join(skill.output_schema)
    instruction = (
        "你是建筑方案前期的项目 AI 执行器。必须围绕当前项目回答，避免通用空话。\n"
        "判断、研判、转译、方案、风险和复用类内容要优先基于项目上下文与知识库来源；不要编造来源。\n"
        "请输出 JSON，不要输出 Markdown。字段尽量贴合以下 schema："
        f"{schema_hint}。\n"
    )
    payload = {
        "skill": {"id": skill.id, "name": skill.name, "description": skill.description},
        "user_request": prompt,
        "project_context": context,
        "retrieved_sources": sources,
    }
    try:
        raw = await call_deepseek_text(
            prompt=json.dumps(payload, ensure_ascii=False, default=str),
            system_prompt=instruction,
        )
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            parsed = safe_json_parse(match.group(0), default={}, field_name="skill_output_json")
            if isinstance(parsed, dict):
                if sources and "sources" not in parsed:
                    parsed["sources"] = sources
                return parsed
    except Exception:
        pass
    return _fallback_skill_output(skill, project, prompt, sources)


async def _generate_image_asset(project: models.Project, prompt: str, output: dict[str, Any]) -> dict[str, Any]:
    image_prompt = (
        output.get("positive_prompt")
        or output.get("prompt")
        or prompt
        or f"{project.name} 建筑方案前期意向图"
    )
    prompt_variants = output.get("prompt_variants") or [{"view": "默认视角", "prompt": image_prompt}]
    result: dict[str, Any] = {
        "provider": settings.image_provider,
        "model": settings.image_model,
        "prompt": image_prompt,
        "prompt_variants": prompt_variants,
        "image_paths": [],
        "status": "not_configured",
        "message": "图片生成服务未配置；已保留多视角提示词，可配置 key 后重试。",
    }
    if not settings.image_configured:
        return result

    target_dir = project_upload_dir(project.id) / "generated-images"
    target_dir.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {settings.image_api_key}"}
    try:
        image_paths = []
        async with httpx.AsyncClient(timeout=120) as client:
            for variant in prompt_variants[:4]:
                variant_prompt = variant.get("prompt") or image_prompt
                body = {
                    "model": settings.image_model,
                    "prompt": variant_prompt,
                    "n": 1,
                    "size": "1024x1024",
                }
                response = await client.post(f"{settings.image_base_url.rstrip('/')}/images/generations", headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
                first = (data.get("data") or [{}])[0]
                image_bytes = b""
                if first.get("b64_json"):
                    image_bytes = base64.b64decode(first["b64_json"])
                elif first.get("url"):
                    image_response = await client.get(first["url"])
                    image_response.raise_for_status()
                    image_bytes = image_response.content
                if not image_bytes:
                    raise RuntimeError("图片服务未返回可保存的图片数据")
                file_path = target_dir / f"ai-image-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}.png"
                file_path.write_bytes(image_bytes)
                image_paths.append(str(file_path))
            result.update({"image_paths": image_paths, "status": "succeeded", "message": f"已生成 {len(image_paths)} 张多视角图片。"})
    except Exception as exc:
        result.update({"status": "failed", "message": f"图片生成失败：{exc}"})
    return result


async def _execute_skill(db: Session, project: models.Project, skill: SkillDefinition, prompt: str, intent_meta: Optional[dict[str, Any]] = None) -> models.SkillCard:
    context = _project_context_pack(project)
    query = " ".join([prompt, project.name, project.city, project.project_type, project.phase]).strip()
    chunks = search_knowledge(db, query, limit=8) if (skill.retrieval_required and query) else []
    sources = _skill_source_refs(chunks, project)
    output = await _deepseek_skill_output(skill, project, prompt, context, sources)

    if skill.id == "ai_image_generation":
        prompt_skill = SKILL_BY_ID.get("image_prompt")
        prompt_output = await _deepseek_skill_output(prompt_skill or skill, project, prompt, context, sources)
        multiview = build_multiview_image_prompts(project, user_prompt=prompt, sources=sources)
        prompt_output = {**prompt_output, **multiview}
        image_result = await _generate_image_asset(project, prompt, prompt_output)
        output = {**prompt_output, **image_result, "source_context": sources}

    markdown = _markdown_from_output(skill, output, prompt)
    input_payload = {
        "prompt": prompt,
        "project_id": project.id,
        "skill": skill.id,
        "intent": intent_meta or {},
        "context_counts": context.get("counts", {}),
    }
    card = models.SkillCard(
        project_id=project.id,
        card_type=skill.id,
        title=skill.name,
        status="succeeded" if output.get("status") not in {"failed", "not_configured"} else output.get("status", "succeeded"),
        input_json=json.dumps(input_payload, ensure_ascii=False, default=str),
        output_json=json.dumps(output, ensure_ascii=False, default=str),
        markdown=markdown,
        source="huashu" if skill.id == "ai_image_generation" else ("mock" if settings.mock_mode else "deepseek"),
        completed_at=utc_now(),
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def run_skill_card(db: Session, project: models.Project, card_type: str, prompt: str = "") -> models.SkillCard:
    skill_id = _normalize_skill_id(card_type)
    skill = SKILL_BY_ID.get(skill_id, SKILL_BY_ID["task_breakdown"])
    sources = _skill_source_refs([], project)
    output = _fallback_skill_output(skill, project, prompt, sources)
    markdown = _markdown_from_output(skill, output, prompt)
    card = models.SkillCard(
        project_id=project.id,
        card_type=skill.id,
        title=skill.name,
        status="succeeded",
        input_json=json.dumps({"prompt": prompt, "project_id": project.id, "skill": skill.id}, ensure_ascii=False),
        output_json=json.dumps(output, ensure_ascii=False, default=str),
        markdown=markdown,
        source="local_skill",
        completed_at=utc_now(),
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


async def run_agent_chat(db: Session, project: models.Project, message: str, requested_skill: str = "") -> dict[str, Any]:
    if requested_skill:
        skill = SKILL_BY_ID.get(_normalize_skill_id(requested_skill), SKILL_BY_ID["task_breakdown"])
        confidence = 1.0
        reason = "用户直接指定技能。"
    else:
        skill, confidence, reason = match_skill_by_keywords(message)
        if confidence < 0.5 and not settings.mock_mode:
            try:
                choices = list_builtin_skills()
                raw = await call_deepseek_text(
                    prompt=json.dumps({"message": message, "skills": choices}, ensure_ascii=False),
                    system_prompt=(
                        "请为建筑设计 AI 代理选择最合适的 skill。只输出 JSON："
                        '{"intent":"skill_id","confidence":0.0到1.0,"reason":"原因"}。'
                    ),
                )
                match = re.search(r"\{.*\}", raw, re.S)
                if match:
                    payload = safe_json_parse(match.group(0), default={}, field_name="skill_selection_json")
                    candidate = SKILL_BY_ID.get(_normalize_skill_id(str(payload.get("intent") or "")))
                    if candidate:
                        skill = candidate
                        confidence = float(payload.get("confidence") or confidence)
                        reason = str(payload.get("reason") or reason)
            except Exception:
                pass
    card = await _execute_skill(db, project, skill, message, {"confidence": confidence, "reason": reason})
    return {
        "intent": skill.id,
        "confidence": confidence,
        "reason": reason,
        "selected_skill": {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "downstream": list(skill.downstream),
        },
        "card": card,
        "context": _project_context_pack(project).get("counts", {}),
        "available_skills": list_builtin_skills(),
    }
