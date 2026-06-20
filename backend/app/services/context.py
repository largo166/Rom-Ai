"""context.py — 项目上下文包生成、沉淀到知识库"""
import re
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.context_schema import ContextType, SCHEMA_VERSION
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
