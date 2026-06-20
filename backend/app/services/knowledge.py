"""knowledge.py — 知识库索引、检索、统计"""
import logging
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import engine as db_engine
from app.json_safety import safe_json_dump
from app.services.core import (
    DEFAULT_VAULT_EXCLUDE_DIRS,
    DEFAULT_VAULT_EXCLUDE_EXTS,
    DEFAULT_VAULT_MAX_FILE_SIZE,
    KNOWLEDGE_OVERVIEW_TRIGGERS,
    SUPPORTED_KNOWLEDGE_EXTS,
    parse_document,
)

logger = logging.getLogger(__name__)


# ──────────────────────────── 元数据解析 ────────────────────────────

def extract_md_metadata(text: str) -> tuple[str, list[str], list[str]]:
    heading = ""
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            break
    tags = sorted(set(re.findall(r"(?<!\w)#([\w\u4e00-\u9fff/-]+)", text)))
    links = sorted(set(re.findall(r"\[\[([^\]]+)\]\]", text)))
    return heading, tags, links


def chunk_text(text: str, path: str, tags: list[str], links: list[str]) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    chunks = []
    current_heading = ""
    buffer = []
    for line in text.splitlines():
        if line.startswith("#") and buffer:
            content = "\n".join(buffer).strip()
            if content:
                chunks.append({"heading": current_heading, "content": content, "path": path, "tags": tags, "links": links})
            current_heading = line.lstrip("#").strip()
            buffer = [line]
        else:
            if line.startswith("#") and not current_heading:
                current_heading = line.lstrip("#").strip()
            buffer.append(line)
    content = "\n".join(buffer).strip()
    if content:
        chunks.append({"heading": current_heading, "content": content, "path": path, "tags": tags, "links": links})
    final = []
    for chunk in chunks:
        content = chunk["content"]
        if len(content) <= 1600:
            final.append(chunk)
            continue
        for i in range(0, len(content), 1400):
            final.append({**chunk, "content": content[i : i + 1600]})
    return final


def safe_browser_relative_path(filename: str) -> str:
    normalized = filename.replace("\\", "/").lstrip("/")
    parts = [part for part in PurePosixPath(normalized).parts if part not in {"", ".", ".."} and ":" not in part]
    return "/".join(parts) or "uploaded-file"


# ──────────────────────────── 索引 ────────────────────────────

def index_knowledge_file(db: Session, source_path: Path, display_path: Optional[str] = None) -> dict[str, Any]:
    ext = source_path.suffix.lower()
    text, status = parse_document(source_path)
    heading, tags, links = extract_md_metadata(text) if ext == ".md" else ("", [], [])
    indexed_path = display_path or str(source_path)
    record = db.scalar(select(models.KnowledgeFile).where(models.KnowledgeFile.filepath == indexed_path))
    if not record:
        record = models.KnowledgeFile(filepath=indexed_path)
        db.add(record)
        db.flush()
    record.filename = Path(indexed_path).name
    record.filetype = ext.lstrip(".")
    record.filesize = source_path.stat().st_size
    record.title = heading or source_path.stem
    record.folder = str(Path(indexed_path).parent)
    db.execute(delete(models.KnowledgeChunk).where(models.KnowledgeChunk.file_id == record.id))
    db.execute(delete(models.KnowledgeTag).where(models.KnowledgeTag.file_id == record.id))
    db.execute(delete(models.KnowledgeLink).where(models.KnowledgeLink.file_id == record.id))
    for chunk in chunk_text(text, indexed_path, tags, links):
        db.add(
            models.KnowledgeChunk(
                file_id=record.id,
                heading=chunk["heading"],
                content=chunk["content"],
                path=chunk["path"],
                tags=safe_json_dump(chunk["tags"], field_name="chunk_tags"),
                links=safe_json_dump(chunk["links"], field_name="chunk_links"),
            )
        )
    for tag, count in Counter(tags).items():
        db.add(models.KnowledgeTag(file_id=record.id, tag=tag, count=count))
    for link in links:
        db.add(models.KnowledgeLink(file_id=record.id, source_path=indexed_path, target=link))
    return {"filename": record.filename, "path": indexed_path, "filetype": record.filetype, "status": status}


def upsert_knowledge_markdown(db: Session, indexed_path: str, title: str, markdown: str, tags: list[str]) -> models.KnowledgeFile:
    record = db.scalar(select(models.KnowledgeFile).where(models.KnowledgeFile.filepath == indexed_path))
    if not record:
        record = models.KnowledgeFile(filepath=indexed_path)
        db.add(record)
        db.flush()
    record.filename = Path(indexed_path).name
    record.filetype = "md"
    record.filesize = len(markdown.encode("utf-8"))
    record.title = title
    record.folder = str(Path(indexed_path).parent)
    db.execute(delete(models.KnowledgeChunk).where(models.KnowledgeChunk.file_id == record.id))
    db.execute(delete(models.KnowledgeTag).where(models.KnowledgeTag.file_id == record.id))
    db.execute(delete(models.KnowledgeLink).where(models.KnowledgeLink.file_id == record.id))
    for chunk in chunk_text(markdown, indexed_path, tags, []):
        db.add(
            models.KnowledgeChunk(
                file_id=record.id,
                heading=chunk["heading"],
                content=chunk["content"],
                path=chunk["path"],
                tags=safe_json_dump(chunk["tags"], field_name="chunk_tags"),
                links=safe_json_dump(chunk["links"], field_name="chunk_links"),
            )
        )
    for tag, count in Counter(tags).items():
        db.add(models.KnowledgeTag(file_id=record.id, tag=tag, count=count))
    return record


# ──────────────────────────── 扫描 ────────────────────────────

def scan_knowledge_directory(db: Session, directory: Path, clear_existing: bool = False) -> dict[str, Any]:
    if clear_existing:
        db.execute(delete(models.KnowledgeLink))
        db.execute(delete(models.KnowledgeTag))
        db.execute(delete(models.KnowledgeChunk))
        db.execute(delete(models.KnowledgeFile))
        db.commit()
    stats = Counter()
    recent = []
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_KNOWLEDGE_EXTS:
            continue
        ext = path.suffix.lower()
        stats["total_files"] += 1
        stats[ext.lstrip(".") or "other"] += 1
        recent.append(index_knowledge_file(db, path))
    db.commit()
    try:
        from app.retrieval import rebuild_fts_index

        rebuild_fts_index(db_engine)
    except Exception:
        logger.warning("Rebuild FTS5 after scan_knowledge_directory failed (non-fatal)", exc_info=True)
    return {"indexed_files": stats["total_files"], "stats": knowledge_stats(db), "skipped_files": [], "recent_files": recent[:20]}


def should_index_vault_path(path: Path, root: Path, include_sync_notes: bool = False) -> tuple[bool, str]:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    parts = set(relative.parts)
    if parts & DEFAULT_VAULT_EXCLUDE_DIRS:
        return False, "excluded_directory"
    if not include_sync_notes and "笔记同步助手" in parts:
        return False, "sync_notes_optional"
    if path.suffix.lower() not in SUPPORTED_KNOWLEDGE_EXTS:
        return False, "unsupported_type"
    if path.suffix.lower() in DEFAULT_VAULT_EXCLUDE_EXTS:
        return False, "excluded_type"
    try:
        if path.stat().st_size == 0:
            return False, "empty_file"
        if path.stat().st_size > DEFAULT_VAULT_MAX_FILE_SIZE:
            return False, "large_file"
    except OSError:
        return False, "stat_failed"
    return True, "ok"


def scan_vault_directory(
    db: Session,
    directory: Path,
    clear_existing: bool = False,
    include_sync_notes: bool = False,
) -> dict[str, Any]:
    if clear_existing:
        db.execute(delete(models.KnowledgeLink))
        db.execute(delete(models.KnowledgeTag))
        db.execute(delete(models.KnowledgeChunk))
        db.execute(delete(models.KnowledgeFile))
        db.commit()
    stats = Counter()
    skipped = Counter()
    recent = []
    priority_prefixes = ("wiki", "raw", "Obj-")
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        allowed, reason = should_index_vault_path(path, directory, include_sync_notes=include_sync_notes)
        if not allowed:
            skipped[reason] += 1
            continue
        try:
            rel = path.relative_to(directory)
            first = rel.parts[0] if rel.parts else ""
            priority = first == "wiki" or first == "raw" or first.startswith("Obj-")
        except ValueError:
            priority = False
        indexed = index_knowledge_file(db, path)
        indexed["priority_source"] = priority
        recent.append(indexed)
        stats["total_files"] += 1
        stats[path.suffix.lower().lstrip(".") or "other"] += 1
        if any(str(path).find(prefix) >= 0 for prefix in priority_prefixes):
            stats["priority_files"] += 1
    db.commit()
    try:
        from app.retrieval import rebuild_fts_index

        rebuild_fts_index(db_engine)
    except Exception:
        logger.warning("Rebuild FTS5 after scan_vault_directory failed (non-fatal)", exc_info=True)
    return {
        "indexed_files": stats["total_files"],
        "stats": knowledge_stats(db),
        "skipped": dict(skipped),
        "skipped_files": [{"reason": reason, "count": count} for reason, count in skipped.items()],
        "recent_files": recent[:30],
        "filters": {
            "excluded_dirs": sorted(DEFAULT_VAULT_EXCLUDE_DIRS),
            "max_file_mb": DEFAULT_VAULT_MAX_FILE_SIZE // 1024 // 1024,
            "include_sync_notes": include_sync_notes,
        },
    }


def scan_vault_directory_with_progress(
    db: Session,
    directory: Path,
    clear_existing: bool = False,
    include_sync_notes: bool = False,
    progress: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if clear_existing:
        db.execute(delete(models.KnowledgeLink))
        db.execute(delete(models.KnowledgeTag))
        db.execute(delete(models.KnowledgeChunk))
        db.execute(delete(models.KnowledgeFile))
        db.commit()
    stats = Counter()
    skipped = Counter()
    recent = []
    paths = [path for path in directory.rglob("*") if path.is_file()]
    total = len(paths)
    if progress is not None:
        progress.update({"total_candidates": total, "processed": 0, "indexed_files": 0, "skipped_files": 0})
    priority_prefixes = ("wiki", "raw", "Obj-")
    for index, path in enumerate(paths, start=1):
        if progress is not None:
            progress.update({"processed": index, "current_file": str(path)})
        allowed, reason = should_index_vault_path(path, directory, include_sync_notes=include_sync_notes)
        if not allowed:
            skipped[reason] += 1
            if progress is not None:
                progress["skipped_files"] = sum(skipped.values())
            continue
        try:
            rel = path.relative_to(directory)
            first = rel.parts[0] if rel.parts else ""
            priority = first == "wiki" or first == "raw" or first.startswith("Obj-")
        except ValueError:
            priority = False
        indexed = index_knowledge_file(db, path)
        indexed["priority_source"] = priority
        recent.append(indexed)
        stats["total_files"] += 1
        stats[path.suffix.lower().lstrip(".") or "other"] += 1
        if any(str(path).find(prefix) >= 0 for prefix in priority_prefixes):
            stats["priority_files"] += 1
        if progress is not None:
            progress["indexed_files"] = stats["total_files"]
        if stats["total_files"] % 25 == 0:
            db.commit()
    db.commit()
    try:
        from app.retrieval import rebuild_fts_index

        rebuild_fts_index(db_engine)
    except Exception:
        logger.warning("Rebuild FTS5 after scan_vault_directory_with_progress failed (non-fatal)", exc_info=True)
    result = {
        "indexed_files": stats["total_files"],
        "stats": knowledge_stats(db),
        "skipped": dict(skipped),
        "skipped_files": [{"reason": reason, "count": count} for reason, count in skipped.items()],
        "recent_files": recent[:30],
        "filters": {
            "excluded_dirs": sorted(DEFAULT_VAULT_EXCLUDE_DIRS),
            "max_file_mb": DEFAULT_VAULT_MAX_FILE_SIZE // 1024 // 1024,
            "include_sync_notes": include_sync_notes,
        },
    }
    if progress is not None:
        progress.update({"processed": total, "current_file": "", "result": result})
    return result


# ──────────────────────────── 统计 / 概览 ────────────────────────────

def knowledge_overview(db: Session) -> dict[str, Any]:
    stats = knowledge_stats(db)
    files = list(db.scalars(select(models.KnowledgeFile).order_by(models.KnowledgeFile.updated_at.desc()).limit(80)))
    folder_counts = Counter(file.folder or "未分组" for file in files)
    type_counts = stats.get("filetype_distribution", {})
    recent = [
        {
            "filename": file.filename,
            "filepath": file.filepath,
            "filetype": file.filetype,
        }
        for file in files[:12]
    ]
    return {
        "stats": stats,
        "top_folders": [{"folder": folder, "count": count} for folder, count in folder_counts.most_common(10)],
        "type_counts": type_counts,
        "recent_files": recent,
    }


def is_knowledge_overview_question(question: str) -> bool:
    normalized = question.strip().replace("？", "").replace("?", "")
    return any(trigger in normalized for trigger in KNOWLEDGE_OVERVIEW_TRIGGERS)


def knowledge_overview_answer(db: Session) -> tuple[str, list[dict[str, Any]]]:
    overview = knowledge_overview(db)
    stats = overview["stats"]
    if not stats.get("total_files"):
        return "知识库目前还没有索引内容。请先索引本地路径或上传文件夹。", []
    type_counts = stats.get("filetype_distribution", {})
    type_text = "、".join(f"{key}: {value}" for key, value in sorted(type_counts.items())) or "暂无类型统计"
    folder_lines = "\n".join(f"- {item['folder']}：{item['count']} 个近期文件" for item in overview["top_folders"][:8])
    recent_lines = "\n".join(f"- {item['filename']}（{item['filetype']}）\n  {item['filepath']}" for item in overview["recent_files"][:8])
    answer = (
        "你的知识库当前已建立索引，可以从整体结构上这样理解：\n\n"
        f"- 总文件：{stats['total_files']} 个\n"
        f"- Markdown：{stats['markdown_files']} 个\n"
        f"- PDF / Word / Excel：{stats['pdf_docx_xlsx_files']} 个\n"
        f"- 图片：{stats['image_files']} 个\n"
        f"- 双链：{stats['link_count']} 条\n"
        f"- 文件类型分布：{type_text}\n\n"
        "近期资料主要分布在：\n"
        f"{folder_lines or '- 暂无分组'}\n\n"
        "最近索引的代表文件：\n"
        f"{recent_lines or '- 暂无文件'}\n\n"
        "你可以继续问更具体的问题，例如某个项目、某类规范、某个阶段任务或某份文件。"
    )
    refs = [
        {
            "chunk_id": "",
            "file_name": item["filename"],
            "file_path": item["filepath"],
            "quote": "知识库概览代表文件",
            "heading": "",
        }
        for item in overview["recent_files"][:8]
    ]
    return answer, refs


def knowledge_stats(db: Session) -> dict[str, Any]:
    files = list(db.scalars(select(models.KnowledgeFile)))
    tags = list(db.scalars(select(models.KnowledgeTag)))
    links_count = db.scalar(select(func.count(models.KnowledgeLink.id))) or 0
    type_counts = Counter(file.filetype for file in files)
    top_tags = Counter()
    for tag in tags:
        top_tags[tag.tag] += tag.count
    return {
        "total_files": len(files),
        "markdown_files": type_counts.get("md", 0),
        "pdf_docx_xlsx_files": type_counts.get("pdf", 0) + type_counts.get("docx", 0) + type_counts.get("xlsx", 0),
        "image_files": type_counts.get("png", 0) + type_counts.get("jpg", 0) + type_counts.get("jpeg", 0),
        "filetype_distribution": dict(type_counts),
        "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags.most_common(20)],
        "link_count": links_count,
    }


def knowledge_tree(db: Session) -> list[dict[str, Any]]:
    files = list(db.scalars(select(models.KnowledgeFile).order_by(models.KnowledgeFile.filepath)))
    roots: dict[str, Any] = {}
    for file in files:
        parts = Path(file.filepath).parts
        current = roots
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current.setdefault("_files", []).append({"name": file.filename, "path": file.filepath, "filetype": file.filetype})

    def pack(name: str, value: Any) -> dict[str, Any]:
        children = [pack(k, v) for k, v in value.items() if k != "_files"]
        files_nodes = [{"name": f["name"], "type": "file", "path": f["path"], "filetype": f["filetype"]} for f in value.get("_files", [])]
        return {"name": name, "type": "folder", "children": children + files_nodes}

    return [pack(k, v) for k, v in roots.items()]


def list_knowledge_files(db: Session, q: str = "", limit: int = 100) -> dict[str, Any]:
    safe_limit = max(1, min(limit or 100, 500))
    query = select(models.KnowledgeFile).order_by(models.KnowledgeFile.updated_at.desc())
    if q.strip():
        keyword = f"%{q.strip()}%"
        query = query.where(or_(models.KnowledgeFile.filename.like(keyword), models.KnowledgeFile.filepath.like(keyword)))
    all_items = list(db.scalars(query))
    items = all_items[:safe_limit]
    return {
        "total": len(all_items),
        "items": [
            {
                "id": item.id,
                "filename": item.filename,
                "filepath": item.filepath,
                "filetype": item.filetype,
                "filesize": item.filesize,
                "updated_at": item.updated_at,
            }
            for item in items
        ],
    }


def search_knowledge(db: Session, question: str, limit: int = 6) -> list[models.KnowledgeChunk]:
    """
    知识库检索：优先使用 FTS5/BM25，失败时降级到 ilike。
    Phase 6 将原有 inline FTS5 逻辑统一收敛到 FTS5RetrievalEngine。
    """
    terms = [term for term in re.split(r"\s+", question.strip()) if term]

    # 1) FTS5 检索（通过 RetrievalEngine 接口）
    if terms and settings.database_url.startswith("sqlite"):
        try:
            from app.retrieval import FTS5RetrievalEngine

            retrieval = FTS5RetrievalEngine(db.get_bind() or db_engine)
            fts_query = " ".join(terms[:12])
            results = retrieval.search(fts_query, top_k=limit)
            if results:
                ids = [r["chunk_id"] for r in results if r.get("chunk_id")]
                if ids:
                    by_id = {
                        chunk.id: chunk
                        for chunk in db.scalars(
                            select(models.KnowledgeChunk).where(models.KnowledgeChunk.id.in_(ids))
                        )
                    }
                    ordered = [by_id[item_id] for item_id in ids if item_id in by_id]
                    if ordered:
                        return ordered
        except Exception:
            logger.warning("FTS5 search failed, falling back to ilike", exc_info=True)
            db.rollback()

    # 2) 降级：ilike 模糊匹配
    query = select(models.KnowledgeChunk)
    if terms:
        clauses = []
        for term in terms[:6]:
            clauses.append(models.KnowledgeChunk.content.ilike(f"%{term}%"))
            clauses.append(models.KnowledgeChunk.heading.ilike(f"%{term}%"))
        query = query.where(or_(*clauses))
    chunks = list(db.scalars(query.limit(limit)))
    if chunks or not terms:
        return chunks

    # 3) 最后兜底：返回最新更新的片段
    return list(db.scalars(select(models.KnowledgeChunk).order_by(models.KnowledgeChunk.updated_at.desc()).limit(limit)))


def _markdown_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _refs_from_chunks(chunks: list[models.KnowledgeChunk]) -> list[dict[str, Any]]:
    refs = []
    for chunk in chunks:
        refs.append(
            {
                "chunk_id": chunk.id,
                "source_file": Path(chunk.path).name,
                "source_path": chunk.path,
                "heading": chunk.heading,
                "quote": chunk.content[:420],
                "relevance_score": 0.82,
            }
        )
    return refs
