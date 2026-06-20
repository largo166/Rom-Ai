"""inbox.py — 收件箱扫描、分类、归档"""
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.json_safety import safe_json_dump
from app.services.core import (
    SUPPORTED_INBOX_EXTS,
    SUPPORTED_PROJECT_EXTS,
    _unique_path,
    file_sha256,
    inbox_upload_dir,
    parse_document,
    project_upload_dir,
)
from app.services.knowledge import index_knowledge_file


# ──────────────────────────── 常量 ────────────────────────────

PROJECT_TOPIC_WORDS = {
    "项目汇报",
    "汇报",
    "方案设计",
    "概念方案设计",
    "概念方案",
    "方案",
    "定位报告",
    "总图及户型",
    "总图",
    "户型",
    "附件",
    "配套",
    "竞品",
    "集",
    "最终版",
    "新定案",
}

KNOWLEDGE_RECOMMENDED_TYPES = {"技术条件", "会议资料", "审核反馈", "项目基础资料", "参考案例", "复盘沉淀"}
KNOWLEDGE_SKIPPED_REASONS = {
    "设计源文件": "设计源文件默认只做项目资产记录。",
    "压缩包与杂项": "压缩包与杂项默认只做项目资产记录。",
    "设计过程": "设计过程稿默认先归档到项目，确认为可复用成果后再入知识库。",
}


# ──────────────────────────── 内部工具 ────────────────────────────

def _read_small_context(path: Path, limit: int = 4000) -> str:
    if path.suffix.lower() not in SUPPORTED_PROJECT_EXTS:
        return ""
    text, status = parse_document(path)
    if status != "parsed":
        return ""
    return text[:limit]


def _pick_material_type(text: str, ext: str) -> tuple[str, list[str]]:
    rules = [
        ("会议资料", ["会议纪要", "参会人", "议题", "会议录音", "转写", "启动会"]),
        ("技术条件", ["日照", "退界", "容积率", "消防", "规划条件", "人防", "绿建", "管线"]),
        ("参考案例", ["竞品", "案例", "参考", "市场定位"]),
        ("审核反馈", ["甲方意见", "修改意见", "审核", "反馈", "批注", "问题清单"]),
        ("交付成果", ["汇报", "提案", "投标", "正式提交", "盖章版", "交付"]),
        ("项目基础资料", ["设计任务书", "红线", "面积表", "合同", "甲方需求", "用地"]),
    ]
    if ext in {".zip", ".rar", ".7z"}:
        return "压缩包与杂项", ["压缩包待确认"]
    if ext in {".dwg", ".skp", ".rvt"}:
        return "设计源文件", ["设计源文件仅登记资产"]
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return "设计过程", ["图片资料默认先做项目资产"]
    for material_type, keywords in rules:
        hits = [word for word in keywords if word in text]
        if hits:
            return material_type, hits
    if ext in {".pptx", ".pdf"}:
        return "设计过程", ["按文件类型判断"]
    return "项目基础资料", ["默认归入基础资料"]


def _strip_project_topic_words(text: str) -> str:
    value = re.sub(r"\.[^.]+$", "", text)
    value = re.sub(r"20\d{2}[-年.]?\d{1,2}[-月.]?\d{0,2}日?", "", value)
    value = re.sub(r"26\d{4}", "", value)
    value = re.sub(r"0115|0103|0114|0118|V\d+|v\d+", "", value)
    value = re.sub(r"附件\s*\d*[：:、-]?", "", value)
    value = re.sub(r"[（(][^）)]*[）)]", "", value)
    for word in sorted(PROJECT_TOPIC_WORDS, key=len, reverse=True):
        value = value.replace(word, "")
    value = re.sub(r"[_\-\s]+", "", value)
    value = re.sub(r"[：:、，,。]+", "", value)
    return value.strip()


def _canonical_project_name_from_text(filename: str, context: str = "") -> str:
    haystack = f"{filename}\n{context}"
    if "振三街" in haystack:
        if "石家庄" in haystack:
            return "石家庄市振三街地块项目"
        return "振三街项目"
    patterns = [
        r"([\u4e00-\u9fa5]{2,12}(?:市|区|县)?[\u4e00-\u9fa5A-Za-z0-9]{1,18}(?:地块|项目))",
        r"([\u4e00-\u9fa5A-Za-z0-9]{2,24}(?:项目|地块))",
    ]
    for pattern in patterns:
        match = re.search(pattern, haystack)
        if match:
            candidate = _strip_project_topic_words(match.group(1))
            if candidate:
                if candidate.endswith("地块"):
                    return f"{candidate}项目"
                return candidate[:32]
    stem = Path(filename).stem
    cleaned = _strip_project_topic_words(stem)
    parts = [part for part in re.split(r"[_\-\s]+", cleaned) if part]
    stop_words = {"启动会", "会议纪要", "规划条件", "日照退界", "日照分析", "设计任务书"}
    useful = [part for part in parts if part not in stop_words]
    return (useful[0] if useful else cleaned or stem)[:32]


def _extract_project_hint(filename: str, context: str = "") -> str:
    return _canonical_project_name_from_text(filename, context)


def _extract_date_token(text: str) -> str:
    match = re.search(r"(20\d{2})[-年.]?(\d{1,2})[-月.]?(\d{1,2})?", text)
    if not match:
        return datetime.now().strftime("%Y%m%d")
    year, month, day = match.group(1), match.group(2), match.group(3) or "01"
    return f"{year}{int(month):02d}{int(day):02d}"


def _safe_filename_part(text: str, fallback: str = "资料") -> str:
    value = re.sub(r"[\\/:*?\"<>|\s]+", "", text or "")
    return value[:32] or fallback


def _knowledge_recommendation(material_type: str, filename: str = "", text: str = "") -> tuple[bool, str]:
    haystack = f"{filename}\n{text}"
    if material_type in {"设计源文件", "压缩包与杂项", "设计过程"}:
        return False, KNOWLEDGE_SKIPPED_REASONS.get(material_type, "该资料默认只归档到项目。")
    project_specific_words = ["项目汇报", "方案设计", "概念方案", "总图", "户型", "阶段性方案", "汇报稿"]
    reusable_rules = [
        ("规划条件", "包含规划条件，具备跨项目复用价值，可供后续项目参考。"),
        ("退界", "包含退界要求，具备跨项目复用价值，可供后续项目参考。"),
        ("日照", "包含日照要求，具备跨项目复用价值，可供后续项目参考。"),
        ("消防", "包含消防条件，具备跨项目复用价值，可供后续项目参考。"),
        ("人防", "包含人防条件，具备跨项目复用价值，可供后续项目参考。"),
        ("绿建", "包含绿建要求，具备跨项目复用价值，可供后续项目参考。"),
        ("建筑面积计算规则", "包含地方规则或面积计算规则，建议进入知识库。"),
        ("会议结论", "包含会议结论，建议进入知识库。"),
        ("审核意见", "包含审核意见，建议进入知识库。"),
        ("甲方反馈", "包含甲方反馈，建议进入知识库。"),
        ("复盘", "包含复盘方法，建议进入知识库。"),
        ("竞品", "包含竞品或市场定位结论，建议进入知识库。"),
        ("市场定位", "包含竞品或市场定位结论，建议进入知识库。"),
        ("定位报告", "包含竞品或市场定位结论，建议进入知识库。"),
    ]
    if any(word in filename for word in project_specific_words):
        if any(word in haystack for word in ["规划条件", "建筑面积计算规则", "审核意见", "甲方反馈", "会议结论", "复盘", "竞品", "市场定位", "定位报告"]):
            for word, reason in reusable_rules:
                if word in haystack:
                    return True, f"建议入库：{reason}"
        return False, "仅项目归档：这是本项目阶段性方案或汇报资料，复用价值有限。"
    for word, reason in reusable_rules:
        if word in haystack:
            return True, f"建议入库：{reason}"
    if material_type in {"会议资料", "审核反馈", "参考案例"}:
        return True, f"建议入库：{material_type}通常具备复用价值。"
    return False, "仅项目归档：未识别到明确可复用的技术条件、反馈、复盘或规则内容。"


def _same_file_hash(path: str, expected_hash: str) -> bool:
    if not path or not expected_hash:
        return False
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return False
    try:
        return file_sha256(candidate) == expected_hash
    except Exception:
        return False


def _detect_duplicate(db: Session, item: models.InboxItem) -> tuple[str, str, str]:
    file_hash = item.file_hash or (file_sha256(Path(item.temp_path)) if item.temp_path else "")
    if not file_hash:
        return "", "", ""
    for project_file in db.scalars(select(models.ProjectFile)):
        if _same_file_hash(project_file.filepath, file_hash):
            return "project", project_file.id, ""
    for knowledge_file in db.scalars(select(models.KnowledgeFile)):
        if _same_file_hash(knowledge_file.filepath, file_hash):
            return "knowledge", "", knowledge_file.id
    return "", "", ""


# ──────────────────────────── 公开函数 ────────────────────────────

def create_inbox_item_from_path(db: Session, source_path: Path, target_dir: Optional[Path] = None, source_label: str = "本地路径") -> models.InboxItem:
    source_path = source_path.expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"文件不存在：{source_path}")
    ext = source_path.suffix.lower()
    if ext not in SUPPORTED_INBOX_EXTS:
        raise ValueError(f"不支持的文件类型：{source_path.name}")
    target = _unique_path(target_dir or inbox_upload_dir(), source_path.name)
    shutil.copy2(source_path, target)
    item = models.InboxItem(
        original_filename=source_path.name,
        suggested_filename=source_path.name,
        final_filename="",
        source_path=str(source_path),
        temp_path=str(target),
        source_label=source_label,
        status="待确认",
        needs_review=True,
        file_hash=file_sha256(target),
        archive_group="待确认",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def recommend_inbox_item(db: Session, item: models.InboxItem) -> models.InboxItem:
    if item.temp_path and Path(item.temp_path).exists():
        item.file_hash = item.file_hash or file_sha256(Path(item.temp_path))
    duplicate_scope, duplicate_project_file_id, duplicate_knowledge_file_id = _detect_duplicate(db, item)
    item.duplicate_scope = duplicate_scope
    item.duplicate_project_file_id = duplicate_project_file_id
    item.duplicate_knowledge_file_id = duplicate_knowledge_file_id
    if duplicate_scope:
        item.status = "重复文件"
        item.archive_group = "重复文件"
        item.recommended_action = "重复跳过"
        item.suggest_knowledge = False
        item.recommend_knowledge_reason = "项目库或知识库已存在相同文件，默认跳过。"
        item.needs_review = True
        db.commit()
        db.refresh(item)
        return item

    suggest_knowledge, reason = _knowledge_recommendation(item.material_type, item.original_filename, item.summary)
    item.suggest_knowledge = suggest_knowledge
    item.recommend_knowledge_reason = reason
    if item.project_id and item.confidence >= 0.85:
        item.archive_group = "可直接确认"
        item.recommended_action = "入知识库" if suggest_knowledge else "仅项目归档"
        item.status = "待确认"
        item.needs_review = False
    elif not item.project_id:
        item.archive_group = "未归属项目"
        item.recommended_action = "创建新项目"
        item.status = "未归属项目"
        item.needs_review = True
    else:
        item.archive_group = "需审核"
        item.recommended_action = "需人工确认"
        item.status = "需审核"
        item.needs_review = True
    db.commit()
    db.refresh(item)
    return item


def classify_inbox_item(db: Session, item: models.InboxItem) -> models.InboxItem:
    path = Path(item.temp_path)
    ext = path.suffix.lower()
    context = _read_small_context(path)
    haystack = f"{item.original_filename}\n{context}"
    projects = list(db.scalars(select(models.Project).order_by(models.Project.updated_at.desc())))
    matched_project = None
    evidence: list[str] = []
    confidence = 0.35
    for project in projects:
        if project.name and project.name in haystack:
            matched_project = project
            evidence.append(f"文件名或内容包含项目名：{project.name}")
            confidence = 0.92
            break
        if project.city and project.city in haystack and project.phase and project.phase in haystack:
            matched_project = project
            evidence.append(f"同时匹配城市和阶段：{project.city}/{project.phase}")
            confidence = 0.72
            break

    material_type, keyword_hits = _pick_material_type(haystack, ext)
    evidence.extend([f"关键词：{word}" for word in keyword_hits[:4]])
    project_name = matched_project.name if matched_project else _extract_project_hint(item.original_filename, context)
    phase = matched_project.phase if matched_project else ("强排" if "强排" in haystack else "待确认")
    topic = keyword_hits[0] if keyword_hits else Path(item.original_filename).stem[:12]
    date_token = _extract_date_token(item.original_filename)
    suggested_filename = "_".join(
        [
            _safe_filename_part(project_name, "未归属项目"),
            _safe_filename_part(material_type),
            _safe_filename_part(topic),
            _safe_filename_part(phase),
            date_token,
            "V1",
        ]
    ) + ext

    item.project_id = matched_project.id if matched_project else ""
    item.suggested_project_name = project_name
    item.suggested_city = matched_project.city if matched_project else ""
    item.suggested_project_type = matched_project.project_type if matched_project else ""
    item.suggested_phase = phase
    item.material_type = material_type
    item.summary = (context.strip().replace("\n", " ")[:180] if context else f"{material_type}文件，等待人工确认归档。")
    item.keywords = safe_json_dump(keyword_hits, field_name="keywords")
    item.evidence = "；".join(evidence)
    item.confidence = confidence
    item.status = "待确认" if matched_project else "未归属项目"
    item.needs_review = confidence < 0.85 or not matched_project
    suggest_knowledge, knowledge_reason = _knowledge_recommendation(material_type, item.original_filename, context)
    item.suggest_knowledge = suggest_knowledge
    item.recommend_knowledge_reason = knowledge_reason
    item.suggest_todo = material_type in {"会议资料", "审核反馈"}
    item.suggested_filename = suggested_filename
    if path.exists():
        item.file_hash = item.file_hash or file_sha256(path)
    db.commit()
    db.refresh(item)
    return recommend_inbox_item(db, item)


def delete_inbox_items(db: Session, item_ids: list[str]) -> int:
    items = list(db.scalars(select(models.InboxItem).where(models.InboxItem.id.in_(item_ids))))
    for item in items:
        path = Path(item.temp_path) if item.temp_path else None
        if path and path.exists() and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        db.delete(item)
    db.commit()
    return len(items)


def apply_inbox_items(
    db: Session,
    item_ids: list[str],
    project_id: str = "",
    project_payload: Optional[Any] = None,
    final_filename_by_id: Optional[dict[str, str]] = None,
    material_type_by_id: Optional[dict[str, str]] = None,
    enter_knowledge: bool = False,
    enter_knowledge_by_id: Optional[dict[str, bool]] = None,
    archive_root: Optional[Path] = None,
) -> dict[str, Any]:
    items = list(db.scalars(select(models.InboxItem).where(models.InboxItem.id.in_(item_ids))))
    if not items:
        raise ValueError("没有找到可归档的收件箱文件")
    project = db.get(models.Project, project_id) if project_id else None
    if not project:
        if project_payload is None:
            first = items[0]
            project_payload = type("ProjectPayload", (), {
                "name": first.suggested_project_name or "未命名项目",
                "city": first.suggested_city,
                "project_type": first.suggested_project_type,
                "phase": first.suggested_phase,
                "description": "由文件收件箱创建",
                "status": "active",
            })()
        if hasattr(project_payload, "model_dump"):
            data = project_payload.model_dump()
        elif isinstance(project_payload, dict):
            data = project_payload
        else:
            data = {
                "name": getattr(project_payload, "name", "未命名项目"),
                "city": getattr(project_payload, "city", ""),
                "project_type": getattr(project_payload, "project_type", ""),
                "phase": getattr(project_payload, "phase", ""),
                "description": getattr(project_payload, "description", ""),
                "status": getattr(project_payload, "status", "active"),
            }
        project = models.Project(**data)
        db.add(project)
        db.commit()
        db.refresh(project)

    target_dir = archive_root or project_upload_dir(project.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    final_filename_by_id = final_filename_by_id or {}
    material_type_by_id = material_type_by_id or {}
    files: list[models.ProjectFile] = []
    for item in items:
        final_name = Path(final_filename_by_id.get(item.id) or item.suggested_filename or item.original_filename).name
        if not Path(final_name).suffix:
            final_name += Path(item.original_filename).suffix
        target = _unique_path(target_dir, final_name)
        shutil.copy2(Path(item.temp_path), target)
        text, parse_status = parse_document(target) if target.suffix.lower() in SUPPORTED_PROJECT_EXTS else ("", "saved_no_parse")
        record = models.ProjectFile(
            project_id=project.id,
            filename=target.name,
            filepath=str(target),
            filetype=target.suffix.lower().lstrip("."),
            filesize=target.stat().st_size,
            parsed_text=text,
            parse_status=parse_status,
            analysis_status="pending",
        )
        db.add(record)
        files.append(record)
        item.project_id = project.id
        item.final_filename = target.name
        item.archive_path = str(target)
        item.material_type = material_type_by_id.get(item.id, item.material_type)
        item.status = "已归档"
        item.needs_review = False
        should_enter_knowledge = enter_knowledge or bool((enter_knowledge_by_id or {}).get(item.id))
        if should_enter_knowledge:
            index_knowledge_file(db, target, display_path=f"projects/{project.id}/{target.name}")
            item.status = "已进入知识库"
        item.archive_group = item.status
    db.commit()
    for file in files:
        db.refresh(file)
    for item in items:
        db.refresh(item)
    db.refresh(project)
    return {"project": project, "files": files, "items": items}


def apply_inbox_recommendations(
    db: Session,
    item_ids: list[str],
    force_duplicate_ids: Optional[list[str]] = None,
    archive_root: Optional[Path] = None,
) -> dict[str, Any]:
    force_duplicate_ids = force_duplicate_ids or []
    items = list(db.scalars(select(models.InboxItem).where(models.InboxItem.id.in_(item_ids))))
    files: list[models.ProjectFile] = []
    changed_items: list[models.InboxItem] = []
    skipped_count = 0
    created_project_count = 0
    actionable_groups: dict[tuple[str, str, str], list[models.InboxItem]] = defaultdict(list)
    batch_keys = _batch_project_group_keys(items)
    for item in items:
        item = recommend_inbox_item(db, item)
        if item.archive_group == "重复文件" and item.id not in force_duplicate_ids:
            skipped_count += 1
            changed_items.append(item)
            continue
        if item.recommended_action == "需人工确认":
            skipped_count += 1
            changed_items.append(item)
            continue
        actionable_groups[batch_keys.get(item.id, _item_project_group_key(item))].append(item)

    for group_key, group_items in actionable_groups.items():
        kind, _, project_name = group_key
        project_id = group_items[0].project_id if kind == "existing" else ""
        payload = None
        if not project_id:
            payload = type("ProjectPayload", (), {
                "name": project_name or "未命名项目",
                "city": group_items[0].suggested_city,
                "project_type": group_items[0].suggested_project_type or "住宅",
                "phase": group_items[0].suggested_phase or "待确认",
                "description": f"由文件收件箱根据 {len(group_items)} 个资料创建",
                "status": "active",
            })()
        result = apply_inbox_items(
            db,
            [item.id for item in group_items],
            project_id=project_id,
            project_payload=payload,
            enter_knowledge_by_id={item.id: item.suggest_knowledge for item in group_items},
            archive_root=archive_root,
        )
        files.extend(result["files"])
        changed_items.extend(result["items"])
        if not project_id and result["project"].id:
            created_project_count += 1
    return {
        "files": files,
        "items": changed_items,
        "skipped_count": skipped_count,
        "created_project_count": created_project_count,
    }


def _item_project_group_key(item: models.InboxItem) -> tuple[str, str, str]:
    if item.project_id:
        return ("existing", item.project_id, item.suggested_project_name or "已有项目")
    canonical = _canonical_project_name_from_text(item.original_filename, item.summary)
    return ("new", canonical or item.suggested_project_name or "未命名项目", canonical or item.suggested_project_name or "未命名项目")


def _project_signature(name: str) -> str:
    if "振三街" in name:
        return "振三街"
    value = re.sub(r"(?:项目|地块|强排|方案|设计|总图|户型|规划条件|启动会|会议纪要)", "", name)
    value = re.sub(r"(?:杭州|萧山|杭州市|萧山区|浙江|浙江省|市|区|县)", "", value)
    if len(value) >= 2:
        return value
    value = re.sub(r"(?:^.*市|^.*区|^.*县)", "", name)
    value = re.sub(r"(项目|地块)$", "", value)
    return value or name


def _batch_project_group_keys(items: list[models.InboxItem]) -> dict[str, tuple[str, str, str]]:
    raw_keys = {item.id: _item_project_group_key(item) for item in items}
    by_signature: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for key in raw_keys.values():
        kind, project_key, project_name = key
        if kind == "new":
            by_signature[_project_signature(project_name)].append(key)
    preferred_by_signature: dict[str, tuple[str, str, str]] = {}
    for signature, keys in by_signature.items():
        preferred = sorted(set(keys), key=lambda key: (len(key[2]), "市" in key[2], "地块" in key[2]), reverse=True)[0]
        preferred_by_signature[signature] = preferred
    return {
        item_id: preferred_by_signature.get(_project_signature(key[2]), key) if key[0] == "new" else key
        for item_id, key in raw_keys.items()
    }


def _build_inbox_advice_markdown(
    total_files: int,
    action_counts: dict[str, int],
    project_groups: list[dict[str, Any]],
    knowledge_candidates: list[dict[str, str]],
    duplicates: list[dict[str, str]],
    needs_review: list[dict[str, str]],
) -> str:
    lines = [
        f"本次收件箱共有 {total_files} 个文件。",
        f"建议直接归档 {action_counts['归档文件']} 个，其中需要创建新项目 {action_counts['创建项目']} 个，建议进入知识库 {action_counts['入知识库']} 个。",
    ]
    if duplicates:
        lines.append(f"发现 {len(duplicates)} 个重复文件，默认跳过，避免重复进入项目库或知识库。")
    if needs_review:
        lines.append(f"还有 {len(needs_review)} 个文件需要人工看一眼，主要是项目归属或资料类型不够确定。")
    if project_groups:
        lines.append("按项目归档建议：")
        for group in project_groups[:8]:
            action = "建议创建" if group.get("kind") == "new" else "归入已有"
            lines.append(f"- {action}：{group['project_name']}，{group['file_count']} 个文件，包含 {group['material_summary']}。")
    if knowledge_candidates:
        lines.append(f"知识库建议：优先收录 {len(knowledge_candidates)} 个可复用资料，例如技术条件、会议资料、审核反馈、项目基础资料。")
    return "\n".join(lines)


def build_inbox_batch_advice(db: Session, item_ids: list[str]) -> dict[str, Any]:
    query = select(models.InboxItem).order_by(models.InboxItem.created_at.desc())
    if item_ids:
        query = query.where(models.InboxItem.id.in_(item_ids))
    items = list(db.scalars(query))

    recommended_item_ids: list[str] = []
    knowledge_candidates: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    needs_review: list[dict[str, str]] = []
    grouped_items: dict[tuple[str, str, str], list[models.InboxItem]] = defaultdict(list)
    create_project_keys: set[tuple[str, str, str]] = set()
    batch_keys = _batch_project_group_keys(items)

    for item in items:
        item = recommend_inbox_item(db, item)
        if item.archive_group == "重复文件" or item.recommended_action == "重复跳过":
            duplicates.append(
                {
                    "id": item.id,
                    "filename": item.original_filename,
                    "scope": item.duplicate_scope or "unknown",
                    "reason": item.recommend_knowledge_reason or "已存在相同文件",
                }
            )
            continue
        if item.recommended_action == "需人工确认" or item.archive_group == "需审核":
            needs_review.append(
                {
                    "id": item.id,
                    "filename": item.original_filename,
                    "reason": item.evidence or "项目归属或资料类型不够确定",
                }
            )
            continue

        recommended_item_ids.append(item.id)
        group_key = batch_keys.get(item.id, _item_project_group_key(item))
        grouped_items[group_key].append(item)
        if group_key[0] == "new":
            create_project_keys.add(group_key)
        if item.suggest_knowledge:
            knowledge_candidates.append(
                {
                    "id": item.id,
                    "filename": item.original_filename,
                    "material_type": item.material_type,
                    "reason": item.recommend_knowledge_reason,
                }
            )

    project_groups: list[dict[str, Any]] = []
    for (kind, project_key, project_name), group_items in grouped_items.items():
        material_counts = Counter(item.material_type or "未分类" for item in group_items)
        project_groups.append(
            {
                "kind": kind,
                "project_id": project_key if kind == "existing" else "",
                "project_name": project_name,
                "file_count": len(group_items),
                "knowledge_count": sum(1 for item in group_items if item.suggest_knowledge),
                "item_ids": [item.id for item in group_items],
                "aliases": sorted({item.suggested_project_name for item in group_items if item.suggested_project_name})[:5],
                "material_summary": "、".join(f"{name}{count}个" for name, count in material_counts.most_common(4)),
            }
        )
    project_groups.sort(key=lambda group: group["file_count"], reverse=True)

    action_counts = {
        "归档文件": len(recommended_item_ids),
        "创建项目": len(create_project_keys),
        "入知识库": len(knowledge_candidates),
        "跳过重复": len(duplicates),
        "需审核": len(needs_review),
    }
    markdown = _build_inbox_advice_markdown(
        len(items),
        action_counts,
        project_groups,
        knowledge_candidates,
        duplicates,
        needs_review,
    )
    return {
        "total_files": len(items),
        "recommended_item_ids": recommended_item_ids,
        "action_counts": action_counts,
        "project_groups": project_groups,
        "knowledge_candidates": knowledge_candidates,
        "duplicates": duplicates,
        "needs_review": needs_review,
        "markdown": markdown,
        "mode": "rule",
    }


async def build_inbox_batch_advice_with_ai(db: Session, item_ids: list[str]) -> dict[str, Any]:
    import json
    from app.services.analysis import call_deepseek_text

    advice = build_inbox_batch_advice(db, item_ids)
    if settings.mock_mode or not settings.deepseek_api_key:
        return advice

    query = select(models.InboxItem).order_by(models.InboxItem.created_at.desc())
    if item_ids:
        query = query.where(models.InboxItem.id.in_(item_ids))
    items = list(db.scalars(query))
    file_rows = [
        {
            "文件名": item.original_filename,
            "建议项目": item.suggested_project_name,
            "资料类型": item.material_type,
            "推荐动作": item.recommended_action,
            "是否入知识库": item.suggest_knowledge,
            "重复状态": item.duplicate_scope,
            "摘要": (item.summary or "")[:160],
            "依据": (item.evidence or "")[:160],
        }
        for item in items
    ]
    prompt = f"""
你是 ROM-AI 的项目资料管理员。请根据下面收件箱文件清单，输出一份给项目经理看的整体归档建议。

要求：
1. 不要逐个文件长篇解释，要按项目和资料角色分组。
2. 说明哪些可以直接归档，哪些建议创建新项目，哪些建议进入知识库，哪些需要人工审核。
3. 给出本次归档的总体判断和风险提醒。
4. 不要改变系统已计算的动作，只解释和组织建议。

系统统计：
{json.dumps(advice["action_counts"], ensure_ascii=False)}

文件清单：
{json.dumps(file_rows, ensure_ascii=False)}
""".strip()
    try:
        ai_markdown = await call_deepseek_text(
            prompt,
            "你负责把项目文件收件箱的识别结果整理成清晰、可执行、非技术化的归档建议。",
        )
    except Exception:
        return advice
    if ai_markdown.strip():
        advice["markdown"] = ai_markdown.strip()
        advice["mode"] = "deepseek"
    return advice


def run_inbox_scan_with_progress(
    db: Session,
    root: Path,
    source_label: str,
    days: int = 0,
    progress: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    root = root.expanduser()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"目录不存在：{root}")
    cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60) if days and days > 0 else 0
    if progress is not None:
        progress.update(
            {
                "status": "running",
                "step": "枚举文件",
                "total_candidates": 0,
                "processed": 0,
                "imported_files": 0,
                "unsupported_files": 0,
                "old_files": 0,
                "failed_files": 0,
                "current_file": "",
            }
        )

    candidates: list[Path] = []
    unsupported = 0
    old_files = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        if len(candidates) >= 200:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_INBOX_EXTS:
            unsupported += 1
            continue
        if path.stat().st_mtime < cutoff:
            old_files += 1
            continue
        candidates.append(path)

    if progress is not None:
        progress.update(
            {
                "step": "复制并识别",
                "total_candidates": len(candidates),
                "unsupported_files": unsupported,
                "old_files": old_files,
            }
        )

    imported: list[models.InboxItem] = []
    failed: list[str] = []
    for index, path in enumerate(candidates, start=1):
        if progress is not None:
            progress.update({"processed": index, "current_file": path.name, "step": "复制到收件箱"})
        try:
            item = create_inbox_item_from_path(db, path, inbox_upload_dir(), source_label)
            if progress is not None:
                progress.update({"step": "识别项目和资料类型"})
            imported.append(classify_inbox_item(db, item))
            if progress is not None:
                progress["imported_files"] = len(imported)
        except Exception as exc:
            failed.append(f"{path.name}：{exc}")
            if progress is not None:
                progress["failed_files"] = len(failed)

    if not imported:
        detail = f"未导入文件。目录中不支持格式 {unsupported} 个"
        if old_files:
            detail += f"，超过时间范围 {old_files} 个"
        if failed:
            detail += "，失败：" + "；".join(failed[:5])
        raise ValueError(detail)

    if progress is not None:
        progress.update({"step": "生成整体建议", "current_file": ""})
    advice = build_inbox_batch_advice(db, [item.id for item in imported])
    result = {
        "imported_count": len(imported),
        "items": imported,
        "unsupported_files": unsupported,
        "old_files": old_files,
        "failed_files": failed,
        "batch_advice": advice,
    }
    if progress is not None:
        progress.update(
            {
                "status": "succeeded",
                "step": "完成",
                "processed": len(candidates),
                "current_file": "",
                "result": {
                    "imported_count": len(imported),
                    "unsupported_files": unsupported,
                    "old_files": old_files,
                    "failed_count": len(failed),
                    "batch_advice": advice,
                },
            }
        )
    return result


def generate_batch_archive_plan(
    db: Session,
    item_ids: list = None,
    naming_template: str = "",
    format_markdown: bool = True,
) -> dict:
    """生成批量归档整体方案"""
    from app.services.naming import batch_rename_plan, detect_naming_conflicts

    # 1. 获取待处理项
    if item_ids:
        items = db.execute(
            select(models.InboxItem).where(models.InboxItem.id.in_(item_ids))
        ).scalars().all()
    else:
        items = db.execute(
            select(models.InboxItem).where(models.InboxItem.status == "pending")
        ).scalars().all()

    # 如果 pending 没有结果，则查 "待确认"
    if not items and not item_ids:
        items = db.execute(
            select(models.InboxItem).where(models.InboxItem.status == "待确认")
        ).scalars().all()

    if not items:
        return {"summary": "没有待归档文件", "total_files": 0, "groups": [], "naming_conflicts": []}

    # 2. 对未分类的项先批量分类
    for item in items:
        if not item.suggested_project_name:
            classify_inbox_item(db, item)
            recommend_inbox_item(db, item)

    db.flush()
    # 重新查询获取更新后的数据
    if item_ids:
        items = list(db.execute(
            select(models.InboxItem).where(models.InboxItem.id.in_(item_ids))
        ).scalars().all())
    else:
        items = list(db.execute(
            select(models.InboxItem).where(
                models.InboxItem.status.in_(["pending", "待确认"])
            )
        ).scalars().all())

    # 3. 构建命名方案
    file_infos = []
    for item in items:
        file_infos.append({
            "id": item.id,
            "filename": item.original_filename or "",
            "project": item.suggested_project_name or "未分类",
            "type": item.material_type or "文档",
            "date": (item.created_at or datetime.now()).strftime("%Y%m%d"),
        })

    rename_plan = batch_rename_plan(file_infos)
    conflicts = detect_naming_conflicts(rename_plan)

    # 4. 按项目分组
    groups_dict: dict = {}
    for i, item in enumerate(items):
        rp = rename_plan[i]
        proj = rp["project"]
        if proj not in groups_dict:
            groups_dict[proj] = []

        # 构建目标路径：使用 archive_path 或根据项目名推断
        if item.archive_path:
            target_path = str(Path(item.archive_path).parent) + "/"
        elif item.project_id:
            target_path = f"归档/{proj}/"
        else:
            target_path = f"归档/{proj}/"

        will_format = format_markdown and (item.original_filename or "").lower().endswith(".md")

        groups_dict[proj].append({
            "id": item.id,
            "original_name": item.original_filename or "",
            "new_name": rp["new_name"],
            "target_path": target_path,
            "project": proj,
            "file_type": rp["type"],
            "action": "move_rename",
            "will_format": will_format,
        })

    groups = [
        {"project": k, "file_count": len(v), "files": v}
        for k, v in groups_dict.items()
    ]

    # 5. 生成摘要
    summary = f"共 {len(items)} 个文件，分属 {len(groups)} 个项目。"
    summary += f"命名规则：项目名-类型-日期-序号。"
    if conflicts:
        summary += f" ⚠️ 发现 {len(conflicts)} 个命名冲突需处理。"

    return {
        "summary": summary,
        "total_files": len(items),
        "groups": groups,
        "naming_conflicts": conflicts,
    }
