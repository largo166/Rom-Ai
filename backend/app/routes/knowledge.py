import logging
from pathlib import Path
from threading import Thread
from typing import Optional
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.cloud import mirror_knowledge_upload
from app.config import settings
from app.database import engine, get_db
from app.security import PathValidationError, get_allowed_roots, validate_path
from app.utils import utc_now_iso
from app.retrieval import FTS5RetrievalEngine, rebuild_fts_index
from app.services import (
    MAX_BROWSER_UPLOAD_SIZE,
    SUPPORTED_KNOWLEDGE_EXTS,
    call_deepseek_text,
    index_knowledge_file,
    list_knowledge_files,
    knowledge_stats,
    knowledge_tree,
    knowledge_overview_answer,
    is_knowledge_overview_question,
    safe_browser_relative_path,
    scan_knowledge_directory,
    scan_vault_directory,
    scan_vault_directory_with_progress,
    search_knowledge,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
INDEX_JOBS: dict[str, dict] = {}


@router.post("/scan")
def scan(payload: schemas.KnowledgeScanRequest, db: Session = Depends(get_db)):
    try:
        path = validate_path(payload.path, allowed_bases=get_allowed_roots(), must_exist=True)
    except PathValidationError as e:
        raise HTTPException(status_code=400, detail=f"路径校验失败：{e}")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在：{payload.path}")
    result = scan_knowledge_directory(db, path, clear_existing=payload.clear_existing)
    try:
        rebuild_fts_index(engine)
    except Exception as exc:
        logger.warning("Rebuild FTS5 after scan failed (non-fatal): %s", exc)
    return result


@router.post("/index-vault")
def index_vault(payload: schemas.KnowledgeIndexRequest, db: Session = Depends(get_db)):
    try:
        path = validate_path(
            payload.path or settings.default_vault_path,
            allowed_bases=get_allowed_roots(),
            must_exist=True,
        )
    except PathValidationError as e:
        raise HTTPException(status_code=400, detail=f"路径校验失败：{e}")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在：{path}")
    result = scan_vault_directory(
        db,
        path,
        clear_existing=payload.clear_existing,
        include_sync_notes=payload.include_sync_notes,
    )
    try:
        rebuild_fts_index(engine)
    except Exception as exc:
        logger.warning("Rebuild FTS5 after vault index failed (non-fatal): %s", exc)
    return result


def _run_index_job(job_id: str, path: Path, payload: schemas.KnowledgeIndexRequest) -> None:
    db = next(get_db())
    job = INDEX_JOBS[job_id]
    try:
        job["status"] = "running"
        result = scan_vault_directory_with_progress(
            db,
            path,
            clear_existing=payload.clear_existing,
            include_sync_notes=payload.include_sync_notes,
            progress=job,
        )
        job["status"] = "succeeded"
        job["result"] = result
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
    finally:
        db.close()


@router.post("/index-vault/start")
def start_index_vault(payload: schemas.KnowledgeIndexRequest):
    try:
        path = validate_path(
            payload.path or settings.default_vault_path,
            allowed_bases=get_allowed_roots(),
            must_exist=True,
        )
    except PathValidationError as e:
        raise HTTPException(status_code=400, detail=f"路径校验失败：{e}")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在：{path}")
    job_id = uuid4().hex
    INDEX_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "path": str(path),
        "clear_existing": payload.clear_existing,
        "include_sync_notes": payload.include_sync_notes,
        "total_candidates": 0,
        "processed": 0,
        "indexed_files": 0,
        "skipped_files": 0,
        "current_file": "",
        "created_at": utc_now_iso(),
    }
    Thread(target=_run_index_job, args=(job_id, path, payload), daemon=True).start()
    return INDEX_JOBS[job_id]


@router.get("/index-vault/jobs/{job_id}")
def get_index_job(job_id: str):
    job = INDEX_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="索引任务不存在")
    return job


@router.post("/upload")
async def upload_folder(
    files: list[UploadFile] = File(...),
    clear_existing: bool = Form(False),
    source_label: str = Form("browser-folder"),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="没有收到文件。")
    if clear_existing:
        db.execute(delete(models.KnowledgeLink))
        db.execute(delete(models.KnowledgeTag))
        db.execute(delete(models.KnowledgeChunk))
        db.execute(delete(models.KnowledgeFile))
        db.commit()
    upload_root = settings.upload_root_path / "knowledge_uploads" / source_label
    upload_root.mkdir(parents=True, exist_ok=True)
    indexed = []
    skipped = []
    for upload in files:
        relative = safe_browser_relative_path(upload.filename or "uploaded-file")
        ext = Path(relative).suffix.lower()
        if ext not in SUPPORTED_KNOWLEDGE_EXTS:
            skipped.append({"filename": relative, "reason": "unsupported_type"})
            continue
        content = await upload.read()
        if len(content) > MAX_BROWSER_UPLOAD_SIZE:
            skipped.append({"filename": relative, "reason": "file_too_large"})
            continue
        target = upload_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        mirror_knowledge_upload(
            source_label,
            relative,
            target,
            {"filetype": ext.lstrip("."), "filesize": len(content)},
        )
        display_path = f"{source_label}/{relative}".replace("\\", "/")
        indexed.append(index_knowledge_file(db, target, display_path=display_path))
    db.commit()
    try:
        rebuild_fts_index(engine)
    except Exception as exc:
        logger.warning("Rebuild FTS5 after upload failed (non-fatal): %s", exc)
    return {
        "indexed_files": len(indexed),
        "skipped_files": skipped,
        "stats": knowledge_stats(db),
        "recent_files": indexed[:20],
    }


@router.post("/reindex")
def reindex(payload: schemas.KnowledgeScanRequest, db: Session = Depends(get_db)):
    try:
        path = validate_path(payload.path, allowed_bases=get_allowed_roots(), must_exist=True)
    except PathValidationError as e:
        raise HTTPException(status_code=400, detail=f"路径校验失败：{e}")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在：{payload.path}")
    result = scan_knowledge_directory(db, path, clear_existing=True)
    try:
        rebuild_fts_index(engine)
    except Exception as exc:
        logger.warning("Rebuild FTS5 after reindex failed (non-fatal): %s", exc)
    return result


@router.post("/incremental")
def incremental(payload: schemas.KnowledgeScanRequest, db: Session = Depends(get_db)):
    return scan(payload, db)


@router.post("/clear")
def clear_index(db: Session = Depends(get_db)):
    db.execute(delete(models.KnowledgeLink))
    db.execute(delete(models.KnowledgeTag))
    db.execute(delete(models.KnowledgeChunk))
    db.execute(delete(models.KnowledgeFile))
    db.commit()
    return {"ok": True}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    return knowledge_stats(db)


@router.get("/tree")
def tree(db: Session = Depends(get_db)):
    return {"tree": knowledge_tree(db)}


@router.get("/recent-files")
def recent_files(q: str = "", limit: int = 100, db: Session = Depends(get_db)):
    return list_knowledge_files(db, q=q, limit=limit)


@router.post("/ask")
async def ask(payload: schemas.KnowledgeAskRequest, db: Session = Depends(get_db)):
    if is_knowledge_overview_question(payload.question):
        answer, references = knowledge_overview_answer(db)
        return {"mode": "overview", "answer": answer, "references": references}
    chunks = search_knowledge(db, payload.question)
    references = [
        {
            "chunk_id": chunk.id,
            "file_name": Path(chunk.path).name,
            "file_path": chunk.path,
            "quote": chunk.content[:420],
            "heading": chunk.heading,
        }
        for chunk in chunks
    ]
    if payload.project_id:
        for ref in references[:5]:
            db.add(
                models.KnowledgeReference(
                    project_id=payload.project_id,
                    source_file=ref["file_name"],
                    source_path=ref["file_path"],
                    chunk_id=ref["chunk_id"],
                    quote=ref["quote"],
                    relevance_score=80,
                )
            )
        db.commit()
    mode = "mock" if settings.mock_mode else "deepseek"
    context = "\n\n".join(
        f"来源：{ref['file_path']}\n标题：{ref.get('heading') or ''}\n内容：{ref['quote']}"
        for ref in references
    )
    if not references:
        answer = "没有检索到相关内容。请先扫描或上传知识库资料，或换一个更具体的问题。"
    elif settings.mock_mode:
        answer = "【Mock模式】已基于本地关键词索引找到相关片段。配置 DeepSeek 后会生成完整回答。\n\n"
        answer += "\n".join(f"- {ref['file_name']}：{ref['quote'][:120]}" for ref in references)
    else:
        try:
            answer = await call_deepseek_text(
                prompt=(
                    f"用户问题：{payload.question}\n\n"
                    f"本地知识库检索上下文：\n{context}\n\n"
                    "请只依据上下文回答。回答要适合建筑设计工作，最后列出引用来源路径。"
                ),
                system_prompt="你是建筑知识库问答助手。必须基于用户本地资料回答；不确定时说明缺少资料；不要编造来源。",
            )
        except Exception as exc:
            mode = "deepseek_error"
            answer = (
                "DeepSeek 调用失败，已回退为本地检索摘要。请检查网络、API Key 或模型配置。\n\n"
                + "\n".join(f"- {ref['file_name']}：{ref['quote'][:120]}" for ref in references)
                + f"\n\n错误类型：{exc.__class__.__name__}"
            )
    return {"mode": mode, "answer": answer, "references": references}



# ──────────────────────────────────────────────
#  新增端点：搜索 / 对话 / 索引 / 知识条目
# ──────────────────────────────────────────────


@router.get("/search")
def search_knowledge_items(
    q: str = "",
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """搜索知识库条目（FTS5 全文检索）"""
    retrieval = FTS5RetrievalEngine(engine)
    results = retrieval.search(q, top_k=20) if q.strip() else []
    items = [
        {
            "chunk_id": r["chunk_id"],
            "file_name": Path(r["path"]).name if r["path"] else "",
            "file_path": r["path"],
            "heading": r["title"],
            "quote": r["content"][:520],
            "score": r["score"],
        }
        for r in results
    ]
    return {"items": items, "total": len(items)}


@router.post("/search")
def search_knowledge_chunks(payload: schemas.KnowledgeSearchRequest, db: Session = Depends(get_db)):
    """面向程序流程的知识检索：返回可引用的索引片段（FTS5）。"""
    limit = max(1, min(payload.limit, 20))
    retrieval = FTS5RetrievalEngine(engine)
    results = retrieval.search(payload.question, top_k=limit)
    items = [
        {
            "chunk_id": r["chunk_id"],
            "file_name": Path(r["path"]).name if r["path"] else "",
            "file_path": r["path"],
            "heading": r["title"],
            "quote": r["content"][:520],
            "score": r["score"],
        }
        for r in results
    ]
    return {"items": items, "total": len(items)}


@router.post("/chat")
async def knowledge_chat(payload: schemas.KnowledgeChatRequest, db: Session = Depends(get_db)):
    """知识库对话"""
    from app.mock_data import MOCK_KNOWLEDGE_CHAT_ANSWER
    if settings.mock_mode:
        return {"mode": "mock", **MOCK_KNOWLEDGE_CHAT_ANSWER}

    # 检索相关知识
    chunks = search_knowledge(db, payload.question, limit=6)
    context = "\n\n".join(chunk.content[:500] for chunk in chunks) if chunks else ""

    try:
        answer = await call_deepseek_text(
            prompt=f"用户问题：{payload.question}\n\n知识库上下文：{context}\n\n请基于上下文回答。",
            system_prompt="你是建筑知识库问答助手。必须基于用户本地资料回答；不确定时说明缺少资料。",
        )
        return {"mode": "deepseek", "answer": answer, "sources": [chunk.path for chunk in chunks[:5]]}
    except Exception:
        return {"mode": "mock", **MOCK_KNOWLEDGE_CHAT_ANSWER}


@router.post("/rebuild-fts")
def rebuild_fts_index_endpoint():
    """重建 FTS5 全文索引"""
    try:
        rebuild_fts_index(engine)
        return {"success": True, "message": "FTS5 索引重建完成"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"FTS5 索引重建失败：{exc}")


@router.post("/index")
def index_knowledge_directory(payload: schemas.KnowledgeIndexRequest, db: Session = Depends(get_db)):
    """索引指定目录"""
    try:
        path = validate_path(payload.path, allowed_bases=get_allowed_roots(), must_exist=True)
    except PathValidationError as e:
        raise HTTPException(status_code=400, detail=f"路径校验失败：{e}")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在：{payload.path}")
    result = scan_vault_directory(
        db,
        path,
        clear_existing=payload.clear_existing,
        include_sync_notes=payload.include_sync_notes,
    )
    try:
        rebuild_fts_index(engine)
    except Exception as exc:
        logger.warning("Rebuild FTS5 after index failed (non-fatal): %s", exc)
    return result


@router.get("/items", response_model=list[schemas.KnowledgeItemOut])
def list_knowledge_items(
    project_id: Optional[str] = None,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """获取知识条目列表"""
    query = select(models.KnowledgeItem)
    if project_id:
        query = query.where(models.KnowledgeItem.project_id == project_id)
    if type:
        query = query.where(models.KnowledgeItem.item_type == type)
    query = query.order_by(models.KnowledgeItem.created_at.desc()).limit(50)
    return list(db.scalars(query))
