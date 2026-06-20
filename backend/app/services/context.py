"""context.py — 项目上下文包生成、沉淀到知识库"""
from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.context_schema import ContextType, SCHEMA_VERSION
from app.security import validate_path
from app.services.knowledge import upsert_knowledge_markdown
from app.utils import utc_now_iso


# ──────────────────────────── frontmatter ────────────────────────────

def build_standard_frontmatter(
    type_: ContextType,
    title: str,
    description: str,
    project_id: str,
    tags: list[str],
    *,
    extra: Optional[dict] = None,
) -> str:
    """构造标准 frontmatter（type/title/description/resource/tags/timestamp/schema_version）"""
    fields = {
        "type": type_.value,
        "title": title,
        "description": description,
        "resource": f"project/{project_id}",
        "tags": tags,
        "timestamp": utc_now_iso(),
        "schema_version": SCHEMA_VERSION,
    }
    if extra:
        fields.update(extra)
    lines = ["---"]
    for k, v in fields.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(i) for i in v)}]")
        else:
            lines.append(f'{k}: "{v}"' if isinstance(v, str) else f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


# ──────────────────────────── 迁移 / 日志 / 索引 ────────────────────────────

def _migrate_old_deposit_paths(db, project_id: str):
    """将旧 project-deposits/ 路径迁移到 project-context/（幂等）"""
    old_prefix = f"project-deposits/{project_id}/"
    old_files = db.query(models.KnowledgeFile).filter(
        models.KnowledgeFile.filepath.like(f"{old_prefix}%")
    ).all()
    for f in old_files:
        new_path = f.filepath.replace("project-deposits/", "project-context/", 1)
        existing = db.query(models.KnowledgeFile).filter_by(filepath=new_path).first()
        if existing and existing.id != f.id:
            db.delete(f)
        else:
            f.filepath = new_path
    db.flush()


def append_context_log(db, project_id: str, action: str, files_affected: list[str]):
    """追加一条变更记录到 project-context/{id}/log.md"""
    log_path = f"project-context/{project_id}/log.md"
    entry = f"- [{utc_now_iso()}] {action}: {', '.join(files_affected)}\n"

    existing = db.query(models.KnowledgeFile).filter_by(filepath=log_path).first()
    if existing:
        # 从现有 chunks 重建内容，追加新 entry
        chunks = db.query(models.KnowledgeChunk).filter(
            models.KnowledgeChunk.file_id == existing.id
        ).order_by(models.KnowledgeChunk.id).all()
        reconstructed = "\n\n".join(
            (f"## {c.heading}\n{c.content}" if c.heading else c.content) for c in chunks
        )
        full_content = reconstructed + entry
        upsert_knowledge_markdown(db, log_path, existing.title, full_content, ["changelog", "log"])
    else:
        frontmatter = build_standard_frontmatter(
            ContextType.project_context, "变更台账", "上下文包每次生成/刷新的变更记录",
            project_id, ["changelog", "log"]
        )
        content = frontmatter + "\n\n# 变更台账\n\n" + entry
        upsert_knowledge_markdown(db, log_path, "变更台账", content, ["changelog", "log"])


def regenerate_context_index(db, project_id: str):
    """生成 project-context/{id}/index.md"""
    prefix = f"project-context/{project_id}/"
    files = db.query(models.KnowledgeFile).filter(
        models.KnowledgeFile.filepath.like(f"{prefix}%")
    ).all()

    lines = []
    for f in files:
        if f.filepath.endswith("index.md"):
            continue
        rel = f.filepath.replace(prefix, "")
        desc = f.title or rel
        # 尝试从 chunks 提取 description
        chunks = db.query(models.KnowledgeChunk).filter(
            models.KnowledgeChunk.file_id == f.id
        ).order_by(models.KnowledgeChunk.id).limit(1).all()
        if chunks:
            chunk_content = chunks[0].content[:500]
            if 'description:' in chunk_content:
                m = re.search(r'description:\s*"?([^"\n]+)?"?', chunk_content)
                if m and m.group(1):
                    desc = m.group(1)
        lines.append(f"- [{rel}](./{rel}) — {desc}")

    frontmatter = build_standard_frontmatter(
        ContextType.project_context, "上下文包目录", "包内文件索引，供 agent 逐层浏览",
        project_id, ["index", "directory"]
    )
    body = frontmatter + "\n\n# 上下文包目录\n\n" + "\n".join(sorted(lines)) + "\n"
    index_path = f"{prefix}index.md"
    upsert_knowledge_markdown(db, index_path, "上下文包目录", body, ["index"])


# ──────────────────────────── 启动分析沉淀 ────────────────────────────

def startup_analysis_deposit_markdown(project: models.Project, payload: dict, report_id: str) -> str:
    tags = ["项目沉淀", "启动分析", project.name, project.city, project.project_type, project.phase]
    tags = [tag for tag in tags if tag]
    frontmatter = build_standard_frontmatter(
        ContextType.project_context,
        f"{project.name} 项目分析沉淀",
        "项目启动分析沉淀报告",
        project.id,
        tags,
        extra={"report_id": report_id},
    )
    summary = payload.get("project_summary", {})
    body_lines = [
        f"# {project.name} 项目分析沉淀",
        "",
        "## 项目摘要",
        summary.get("summary") or project.description or "暂无摘要。",
        "",
        "## 可复用技术重点",
    ]
    for card in payload.get("technical_focus_cards", []):
        body_lines.append(f"### {card.get('title') or card.get('dimension') or '技术重点'}")
        body_lines.append(card.get("summary") or "")
        checkpoints = card.get("checkpoints") or []
        if checkpoints:
            body_lines.append("")
            body_lines.append("复核要点：")
            body_lines.extend(f"- {item}" for item in checkpoints)
        source_refs = card.get("source_refs") or []
        if source_refs:
            body_lines.append("")
            body_lines.append("参考来源：")
            body_lines.extend(f"- {item}" for item in source_refs[:6])
        body_lines.append("")
    body_lines.append("## 任务拆解经验")
    for task in payload.get("task_breakdown", []):
        body_lines.append(
            f"- {task.get('task_name', '')}：{task.get('owner_role', '')}，优先级 {task.get('priority', '')}，交付物：{task.get('output_requirement', '')}"
        )
    body_lines.extend(["", "## 风险与待确认问题"])
    body_lines.extend(f"- 风险：{item}" for item in payload.get("risk_list", []))
    body_lines.extend(f"- 待确认：{item}" for item in payload.get("open_questions", []))
    body_lines.extend(["", "## 原始引用来源"])
    for ref in payload.get("source_refs", [])[:12]:
        source = ref.get("source_path") or ref.get("source_file") or "未命名来源"
        quote = ref.get("quote") or ""
        body_lines.append(f"- {source}：{quote[:160]}")
    return frontmatter + "\n\n" + "\n".join(body_lines).strip() + "\n"


def deposit_startup_analysis_to_knowledge(
    db: Session,
    project: models.Project,
    payload: dict,
    report_id: str,
) -> models.KnowledgeFile:
    _migrate_old_deposit_paths(db, project.id)
    title = f"{project.name} 项目分析沉淀"
    indexed_path = f"project-context/{project.id}/startup-analysis.md"
    tags = ["项目沉淀", "启动分析", project.name, project.city, project.project_type, project.phase]
    markdown = startup_analysis_deposit_markdown(project, payload, report_id)
    record = upsert_knowledge_markdown(db, indexed_path, title, markdown, [tag for tag in tags if tag])
    db.flush()
    append_context_log(db, project.id, "startup_analysis_refresh", ["startup-analysis.md"])
    regenerate_context_index(db, project.id)
    return record


# ──────────────────────────── 会议纪要沉淀 ────────────────────────────

def meeting_summary_without_transcript_excerpt(summary: str) -> str:
    marker = "\n## 原始转写摘录\n"
    if marker not in summary:
        return summary
    return summary.split(marker, 1)[0].rstrip()


def meeting_summary_deposit_markdown(project: models.Project, meeting: models.Meeting) -> str:
    tags = ["项目沉淀", "会议纪要", "AI纪要", project.name, meeting.title, project.city, project.project_type, project.phase]
    tags = [tag for tag in tags if tag]
    frontmatter = build_standard_frontmatter(
        ContextType.meeting_summary,
        f"{meeting.title} 纪要摘录",
        "会议纪要摘录",
        project.id,
        tags,
        extra={"meeting_id": meeting.id},
    )
    body_lines = [
        f"# {project.name} - {meeting.title} AI会议纪要",
        "",
        "## AI纪要",
        meeting_summary_without_transcript_excerpt(meeting.summary or "暂无AI纪要。"),
    ]
    actions = meeting.next_actions_json or ""
    if actions:
        body_lines.extend(["", "## 待办", actions])
    if (meeting.transcript or "").strip():
        body_lines.extend(
            [
                "",
                "## 原始转写",
                f"完整转写已独立保存：project-context/{project.id}/meeting-transcripts/{meeting.id}.md",
            ]
        )
    return frontmatter + "\n\n" + "\n".join(body_lines).strip() + "\n"


def deposit_meeting_summary_to_knowledge(
    db: Session,
    project: models.Project,
    meeting: models.Meeting,
) -> models.KnowledgeFile:
    title = f"{project.name} {meeting.title} AI会议纪要"
    indexed_path = f"project-context/{project.id}/meetings/{meeting.id}.md"
    tags = ["项目沉淀", "会议纪要", "AI纪要", project.name, meeting.title, project.city, project.project_type, project.phase]
    markdown = meeting_summary_deposit_markdown(project, meeting)
    record = upsert_knowledge_markdown(db, indexed_path, title, markdown, [tag for tag in tags if tag])
    db.flush()
    append_context_log(db, project.id, "meeting_summary_deposit", [f"meetings/{meeting.id}.md"])
    regenerate_context_index(db, project.id)
    return record


def deposit_meeting_transcript_to_knowledge(
    db: Session,
    project: models.Project,
    meeting: models.Meeting,
) -> Optional[models.KnowledgeFile]:
    transcript = (meeting.transcript or "").strip()
    if not transcript:
        return None
    tags = ["项目沉淀", "会议原始转写", project.name, meeting.title]
    title = f"{project.name} {meeting.title} 原始转写"
    frontmatter = build_standard_frontmatter(
        ContextType.meeting_transcript,
        f"{meeting.title} 原始转写",
        "会议原始转写记录",
        project.id,
        tags,
        extra={"meeting_id": meeting.id},
    )
    indexed_path = f"project-context/{project.id}/meeting-transcripts/{meeting.id}.md"
    markdown = frontmatter + "\n\n" + "\n".join(
        [
            f"# {title}",
            "",
            transcript,
        ]
    ).strip() + "\n"
    record = upsert_knowledge_markdown(db, indexed_path, title, markdown, tags)
    db.flush()
    append_context_log(db, project.id, "meeting_transcript_deposit", [f"meeting-transcripts/{meeting.id}.md"])
    regenerate_context_index(db, project.id)
    return record


# ──────────────────────────── Project Data Link Bundle ────────────────────────────

OKF_VERSION = "0.1"
OKF_BUNDLE_FILES = (
    "project.md",
    "brief.md",
    "site.md",
    "meetings.md",
    "judgement.md",
    "assets.md",
    "agent_context.md",
)


def _json_loads(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _safe_yaml_scalar(value: Any) -> str:
    text = str(value or "").replace('"', '\\"')
    return f'"{text}"'


def _okf_frontmatter(project: models.Project, title: str, updated: datetime, tags: list[str]) -> str:
    fields = [
        ("okf_version", OKF_VERSION),
        ("type", "project_context"),
        ("project_id", project.id),
        ("title", title),
        ("phase", project.phase or ""),
        ("location", project.city or ""),
        ("typology", project.project_type or ""),
    ]
    lines = ["---"]
    for key, value in fields:
        if key in {"okf_version", "type"}:
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {_safe_yaml_scalar(value)}")
    lines.append("tags: [" + ", ".join(_safe_yaml_scalar(tag) for tag in tags if tag) + "]")
    lines.append(f"updated: {_safe_yaml_scalar(updated.isoformat())}")
    lines.append("source: rmo-ai")
    lines.append("---")
    return "\n".join(lines)


def _md_list(items: list[Any], fallback: str = "暂无") -> str:
    clean = [str(item).strip() for item in items if str(item).strip()]
    if not clean:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in clean)


def _project_tags(project: models.Project) -> list[str]:
    tags = [project.name, project.city, project.project_type, project.phase]
    return [tag for tag in tags if tag]


def _latest_report_payload(project: models.Project) -> dict[str, Any]:
    if not project.reports:
        return {}
    latest = max(project.reports, key=lambda item: item.created_at)
    return _json_loads(latest.content_json, {})


def _okf_markdown_documents(project: models.Project, updated: datetime) -> dict[str, str]:
    tags = _project_tags(project)
    report = _latest_report_payload(project)
    client_demands = _json_loads(project.client_demands, [])
    milestones = _json_loads(project.milestones, [])
    deliverables = _json_loads(project.deliverables, [])
    risks = _json_loads(project.risk_summary, [])

    project_md = "\n".join(
        [
            _okf_frontmatter(project, f"{project.name} 项目上下文", updated, tags),
            f"# {project.name}",
            "",
            "## 基本信息",
            f"- 项目名称：{project.name}",
            f"- 地点：{project.city or '待补'}",
            f"- 阶段：{project.phase or '待补'}",
            f"- 类型：{project.project_type or '待补'}",
            f"- 甲方：{project.client_name or '待补'}",
            f"- 联系人：{project.client_contact or '待补'}",
            "",
            "## 项目描述",
            project.description or "暂无项目描述。",
            "",
            "## 里程碑",
            _md_list([item if isinstance(item, str) else item.get("name") or item.get("title") or item for item in milestones]),
            "",
            "## 交付物",
            _md_list([item if isinstance(item, str) else item.get("name") or item.get("title") or item for item in deliverables]),
        ]
    )

    brief_md = "\n".join(
        [
            _okf_frontmatter(project, f"{project.name} 任务书解读", updated, tags + ["brief"]),
            "# 任务书解读",
            "",
            "## 显性需求",
            _md_list(report.get("explicit_requirements", []) if isinstance(report, dict) else []),
            "",
            "## 隐性目标 / 甲方诉求",
            _md_list([
                item.get("raw") or item.get("translation") or str(item) if isinstance(item, dict) else item
                for item in (client_demands if isinstance(client_demands, list) else [])
            ]),
            "",
            "## 矛盾点",
            _md_list(report.get("conflicts", []) if isinstance(report, dict) else []),
            "",
            "## 待追问问题",
            _md_list(report.get("open_questions", []) if isinstance(report, dict) else []),
        ]
    )

    site_md = "\n".join(
        [
            _okf_frontmatter(project, f"{project.name} 场地信息", updated, tags + ["site"]),
            "# 场地信息",
            "",
            "## 已知场地条件",
            project.description or "暂无场地描述。",
            "",
            "## 机会",
            _md_list(report.get("site_opportunities", []) if isinstance(report, dict) else []),
            "",
            "## 限制",
            _md_list(report.get("site_constraints", []) if isinstance(report, dict) else []),
            "",
            "## 待补资料",
            _md_list(report.get("missing_materials", []) if isinstance(report, dict) else []),
        ]
    )

    meeting_lines = []
    for meeting in sorted(project.meetings or [], key=lambda item: item.created_at, reverse=True):
        meeting_lines.extend([
            f"## {meeting.title or '未命名会议'}",
            f"- 时间：{meeting.date.isoformat() if meeting.date else '待补'}",
            f"- 状态：{meeting.status}",
            f"- 类型：{meeting.meeting_type}",
            "",
            meeting.summary or meeting.minutes or meeting.transcript[:1000] or "暂无纪要。",
            "",
        ])
    meetings_md = "\n".join(
        [
            _okf_frontmatter(project, f"{project.name} 会议上下文", updated, tags + ["meetings"]),
            "# 会议与沟通",
            "",
            *(meeting_lines or ["- 暂无会议记录"]),
        ]
    )

    judgement_md = "\n".join(
        [
            _okf_frontmatter(project, f"{project.name} 项目判断", updated, tags + ["judgement"]),
            "# 项目判断",
            "",
            "## 真正的问题",
            report.get("project_basis", "") if isinstance(report, dict) else "暂无判断。",
            "",
            "## 风险",
            _md_list([
                item.get("title") or item.get("detail") or str(item) if isinstance(item, dict) else item
                for item in (risks if isinstance(risks, list) else report.get("risk_list", []) if isinstance(report, dict) else [])
            ]),
            "",
            "## 阶段性结论",
            report.get("project_summary", {}).get("summary", "暂无阶段性结论。") if isinstance(report.get("project_summary"), dict) else "暂无阶段性结论。",
            "",
            "## 下一轮验证点",
            _md_list(report.get("next_actions", []) if isinstance(report, dict) else []),
        ]
    )

    asset_lines = []
    for file in sorted(project.files or [], key=lambda item: item.created_at, reverse=True):
        asset_lines.append(f"- {file.filename}（{file.filetype or 'unknown'}）：{file.filepath}")
    assets_md = "\n".join(
        [
            _okf_frontmatter(project, f"{project.name} 设计输入", updated, tags + ["assets"]),
            "# 设计输入清单",
            "",
            *(asset_lines or ["- 暂无设计输入文件"]),
        ]
    )

    agent_context_md = "\n".join(
        [
            _okf_frontmatter(project, f"{project.name} AI代理上下文", updated, tags + ["agent_context"]),
            "# AI 代理压缩上下文",
            "",
            f"项目：{project.name}",
            f"地点：{project.city or '待补'}",
            f"阶段：{project.phase or '待补'}",
            f"类型：{project.project_type or '待补'}",
            "",
            "## 当前判断",
            report.get("project_summary", {}).get("summary", project.description or "暂无") if isinstance(report.get("project_summary"), dict) else project.description or "暂无",
            "",
            "## 最近会议",
            _md_list([(meeting.summary or meeting.title)[:220] for meeting in (project.meetings or [])[:5]]),
            "",
            "## 当前任务",
            _md_list([task.task_name for task in (project.tasks or [])[:12]]),
            "",
            "## 关键诉求",
            _md_list([
                item.get("raw") or item.get("translation") or str(item) if isinstance(item, dict) else item
                for item in (client_demands if isinstance(client_demands, list) else [])
            ]),
        ]
    )

    return {
        "project.md": project_md,
        "brief.md": brief_md,
        "site.md": site_md,
        "meetings.md": meetings_md,
        "judgement.md": judgement_md,
        "assets.md": assets_md,
        "agent_context.md": agent_context_md,
    }


def _okf_root(project_id: str) -> Path:
    root = settings.upload_root_path / "projects" / project_id / "okf"
    return validate_path(str(root), allowed_bases=[settings.upload_root_path], allow_symlinks=False)


def project_okf_bundle_status(project: models.Project) -> dict[str, Any]:
    root = _okf_root(project.id)
    if not root.exists():
        return {
            "project_id": project.id,
            "generated": False,
            "exists": False,
            "root_path": str(root),
            "root": str(root),
            "updated_at": None,
            "last_updated": None,
            "files": [],
        }
    files = []
    latest: Optional[datetime] = None
    for name in OKF_BUNDLE_FILES:
        path = root / name
        exists = path.exists()
        updated_at = None
        size = 0
        if exists:
            stat = path.stat()
            size = stat.st_size
            updated_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
            file_time = datetime.fromtimestamp(stat.st_mtime)
            latest = file_time if latest is None or file_time > latest else latest
        files.append(
            {
                "name": name,
                "path": str(path),
                "exists": exists,
                "size": size,
                "updated_at": updated_at,
                "indexed_path": f"project-okf/{project.id}/{name}",
            }
        )
    return {
        "project_id": project.id,
        "generated": all(item["exists"] for item in files),
        "exists": all(item["exists"] for item in files),
        "root_path": str(root),
        "root": str(root),
        "updated_at": latest.isoformat() if latest else None,
        "last_updated": latest.isoformat() if latest else None,
        "files": files,
    }


def generate_project_okf_bundle(db: Session, project: models.Project) -> dict[str, Any]:
    root = _okf_root(project.id)
    root.mkdir(parents=True, exist_ok=True)
    updated = datetime.now()
    docs = _okf_markdown_documents(project, updated)
    tags = _project_tags(project) + ["数据链接", "项目资料整理包", "AI可读摘要"]
    for name, markdown in docs.items():
        path = validate_path(str(root / name), allowed_bases=[settings.upload_root_path], allow_symlinks=False)
        path.write_text(markdown, encoding="utf-8")
        indexed_path = f"project-okf/{project.id}/{name}"
        upsert_knowledge_markdown(db, indexed_path, f"{project.name} {name}", markdown, tags + [name.replace(".md", "")])
    append_context_log(db, project.id, "data_link_refresh", list(docs.keys()))
    db.commit()
    try:
        from app.database import engine as db_engine
        from app.retrieval import rebuild_fts_index

        rebuild_fts_index(db_engine)
    except Exception:
        pass
    return project_okf_bundle_status(project)
