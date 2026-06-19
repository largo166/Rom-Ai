from datetime import datetime
from pathlib import Path
import json
import platform
import shutil
import subprocess
from threading import Thread
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import (
    SUPPORTED_INBOX_EXTS,
    apply_inbox_recommendations,
    apply_inbox_items,
    build_inbox_batch_advice_with_ai,
    classify_inbox_item,
    delete_inbox_items,
    inbox_upload_dir,
    recommend_inbox_item,
    run_inbox_scan_with_progress,
)

router = APIRouter(prefix="/api/inbox", tags=["inbox"])
SCAN_JOBS: dict[str, dict] = {}
LOCAL_ORGANIZE_JOBS: dict[str, dict] = {}


def pick_local_folder() -> str:
    if platform.system() == "Darwin":
        script = 'POSIX path of (choose folder with prompt "选择要扫描的项目资料文件夹")'
        result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True)
        if result.returncode == 0:
            return result.stdout.strip()
        if "User canceled" in (result.stderr or ""):
            return ""
        raise RuntimeError((result.stderr or "macOS 文件夹选择器打开失败").strip())
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(title="选择要扫描的项目资料文件夹") or ""
    finally:
        root.destroy()


@router.get("/items", response_model=list[schemas.InboxItemOut])
def list_inbox_items(status: str = "", project_id: str = "", db: Session = Depends(get_db)):
    query = select(models.InboxItem).order_by(models.InboxItem.created_at.desc())
    if status:
        query = query.where(models.InboxItem.status == status)
    if project_id:
        query = query.where(models.InboxItem.project_id == project_id)
    items = list(db.scalars(query))
    for item in items:
        if not item.recommended_action or not item.archive_group or not item.file_hash:
            recommend_inbox_item(db, item)
    return items


@router.post("/pick-folder")
def pick_folder():
    try:
        path = pick_local_folder()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"打开文件夹选择器失败：{exc}") from exc
    return {"path": path, "cancelled": not bool(path)}


@router.post("/upload", response_model=list[schemas.InboxItemOut])
async def upload_inbox_files(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    if not files:
        raise HTTPException(status_code=400, detail="没有收到文件")
    saved = []
    target_dir = inbox_upload_dir()
    for upload in files:
        filename = Path(upload.filename or "uploaded-file").name
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_INBOX_EXTS:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型：{filename}")
        target = target_dir / filename
        if target.exists():
            target = target_dir / f"{target.stem}_{datetime.now().strftime('%H%M%S')}{target.suffix}"
        target.write_bytes(await upload.read())
        item = models.InboxItem(
            original_filename=filename,
            suggested_filename=filename,
            source_path="浏览器上传",
            temp_path=str(target),
            source_label="上传文件",
            status="待确认",
            needs_review=True,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        saved.append(classify_inbox_item(db, item))
    return saved


@router.post("/scan", response_model=list[schemas.InboxItemOut])
def scan_inbox(payload: schemas.InboxScanRequest, db: Session = Depends(get_db)):
    root = Path(payload.path).expanduser() if payload.path else Path.home() / "Downloads"
    try:
        result = run_inbox_scan_with_progress(db, root, payload.source_label, payload.days)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result["items"]


def _run_scan_job(job_id: str, payload: schemas.InboxScanRequest) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    job = SCAN_JOBS[job_id]
    try:
        root = Path(payload.path).expanduser() if payload.path else Path.home() / "Downloads"
        result = run_inbox_scan_with_progress(db, root, payload.source_label, payload.days, job)
        job["status"] = "succeeded"
        job["result"] = {
            "imported_count": result["imported_count"],
            "unsupported_files": result["unsupported_files"],
            "old_files": result["old_files"],
            "failed_count": len(result["failed_files"]),
            "batch_advice": result["batch_advice"],
        }
    except Exception as exc:
        job["status"] = "failed"
        job["step"] = "失败"
        job["error"] = str(exc)
    finally:
        job["updated_at"] = datetime.utcnow().isoformat()
        db.close()


@router.post("/scan/start", response_model=schemas.InboxScanJobOut)
def start_scan_inbox(payload: schemas.InboxScanRequest):
    root = Path(payload.path).expanduser() if payload.path else Path.home() / "Downloads"
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在：{root}")
    job_id = uuid4().hex
    now = datetime.utcnow().isoformat()
    SCAN_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "path": str(root),
        "source_label": payload.source_label,
        "days": payload.days,
        "step": "等待开始",
        "total_candidates": 0,
        "processed": 0,
        "imported_files": 0,
        "unsupported_files": 0,
        "old_files": 0,
        "failed_files": 0,
        "current_file": "",
        "error": "",
        "result": None,
        "created_at": now,
        "updated_at": now,
    }
    Thread(target=_run_scan_job, args=(job_id, payload), daemon=True).start()
    return SCAN_JOBS[job_id]


@router.get("/scan/jobs/{job_id}", response_model=schemas.InboxScanJobOut)
def get_scan_job(job_id: str):
    job = SCAN_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return job


@router.post("/local-organize/start", response_model=schemas.LocalOrganizeJobOut)
async def start_local_organize(payload: schemas.LocalOrganizeStartRequest, db: Session = Depends(get_db)):
    root = Path(payload.path).expanduser()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在：{root}")
    try:
        scan = run_inbox_scan_with_progress(db, root, payload.source_label, payload.days)
        advice = await build_inbox_batch_advice_with_ai(db, [item.id for item in scan["items"]])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"生成本地整理方案失败：{exc}") from exc
    job_id = uuid4().hex
    now = datetime.utcnow().isoformat()
    output_root = root.parent / f"{root.name}_RMO整理_{datetime.now().strftime('%Y%m%d-%H%M')}"
    job = {
        "job_id": job_id,
        "status": "planned",
        "path": str(root),
        "output_root": str(output_root),
        "item_ids": [item.id for item in scan["items"]],
        "advice": advice,
        "manifest_path": "",
        "result": None,
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    LOCAL_ORGANIZE_JOBS[job_id] = job
    return job


@router.get("/local-organize/jobs/{job_id}", response_model=schemas.LocalOrganizeJobOut)
def get_local_organize_job(job_id: str):
    job = LOCAL_ORGANIZE_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="本地整理任务不存在")
    return job


@router.post("/local-organize/apply", response_model=schemas.LocalOrganizeJobOut)
def apply_local_organize(payload: schemas.LocalOrganizeApplyRequest, db: Session = Depends(get_db)):
    job = LOCAL_ORGANIZE_JOBS.get(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="本地整理任务不存在")
    item_ids = payload.selected_item_ids or job.get("item_ids") or []
    if not item_ids:
        raise HTTPException(status_code=400, detail="没有可执行的整理文件")
    output_root = Path(payload.output_root or job["output_root"]).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    try:
        result = apply_inbox_recommendations(db, item_ids, payload.force_duplicate_ids, archive_root=output_root)
        manifest = {
            "job_id": payload.job_id,
            "source_root": job["path"],
            "output_root": str(output_root),
            "created_at": datetime.utcnow().isoformat(),
            "copied_count": len(result["files"]),
            "skipped_count": result["skipped_count"],
            "created_project_count": result["created_project_count"],
            "items": [
                {
                    "id": item.id,
                    "original_filename": item.original_filename,
                    "source_path": item.source_path,
                    "archive_path": item.archive_path,
                    "project_id": item.project_id,
                    "material_type": item.material_type,
                    "status": item.status,
                    "suggest_knowledge": item.suggest_knowledge,
                }
                for item in result["items"]
            ],
        }
        manifest_json = output_root / "RMO-AI归档清单.json"
        manifest_md = output_root / "RMO-AI归档清单.md"
        manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_md.write_text(
            "# RMO-AI归档清单\n\n"
            f"- 来源目录：{job['path']}\n"
            f"- 输出目录：{output_root}\n"
            f"- 复制文件：{manifest['copied_count']}\n"
            f"- 跳过文件：{manifest['skipped_count']}\n"
            f"- 新建项目：{manifest['created_project_count']}\n\n"
            "## 文件明细\n"
            + "\n".join(f"- {item['original_filename']} -> {item['archive_path']}（{item['status']}）" for item in manifest["items"]),
            encoding="utf-8",
        )
        job.update({
            "status": "applied",
            "output_root": str(output_root),
            "manifest_path": str(manifest_md),
            "result": manifest,
            "updated_at": datetime.utcnow().isoformat(),
        })
    except Exception as exc:
        job.update({"status": "failed", "error": str(exc), "updated_at": datetime.utcnow().isoformat()})
        raise HTTPException(status_code=400, detail=f"执行本地整理失败：{exc}") from exc
    return job


@router.get("/scan/latest", response_model=Optional[schemas.InboxScanJobOut])
def latest_scan_job():
    if not SCAN_JOBS:
        return None
    return sorted(SCAN_JOBS.values(), key=lambda job: job.get("created_at", ""), reverse=True)[0]


@router.post("/classify", response_model=list[schemas.InboxItemOut])
def classify_inbox(payload: schemas.InboxClassifyRequest, db: Session = Depends(get_db)):
    query = select(models.InboxItem)
    if payload.item_ids:
        query = query.where(models.InboxItem.id.in_(payload.item_ids))
    items = list(db.scalars(query))
    return [classify_inbox_item(db, item) for item in items]


@router.post("/recommend", response_model=list[schemas.InboxItemOut])
def recommend_inbox(payload: schemas.InboxRecommendRequest, db: Session = Depends(get_db)):
    query = select(models.InboxItem)
    if payload.item_ids:
        query = query.where(models.InboxItem.id.in_(payload.item_ids))
    items = list(db.scalars(query))
    return [recommend_inbox_item(db, item) for item in items]


@router.post("/batch-advice", response_model=schemas.InboxBatchAdviceOut)
async def inbox_batch_advice(payload: schemas.InboxBatchAdviceRequest, db: Session = Depends(get_db)):
    return await build_inbox_batch_advice_with_ai(db, payload.item_ids)


@router.delete("/items/{item_id}")
def delete_inbox_item(item_id: str, db: Session = Depends(get_db)):
    deleted = delete_inbox_items(db, [item_id])
    if not deleted:
        raise HTTPException(status_code=404, detail="收件箱文件不存在")
    return {"deleted": deleted}


@router.post("/delete")
def delete_inbox_batch(payload: schemas.InboxDeleteRequest, db: Session = Depends(get_db)):
    return {"deleted": delete_inbox_items(db, payload.item_ids)}


@router.post("/apply", response_model=schemas.InboxApplyOut)
def apply_inbox(payload: schemas.InboxApplyRequest, db: Session = Depends(get_db)):
    try:
        return apply_inbox_items(
            db,
            payload.item_ids,
            project_id=payload.project_id,
            project_payload=payload.project,
            final_filename_by_id=payload.final_filename_by_id,
            material_type_by_id=payload.material_type_by_id,
            enter_knowledge=payload.enter_knowledge,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/apply-recommendations", response_model=schemas.InboxRecommendationApplyOut)
def apply_recommendations(payload: schemas.InboxApplyRecommendationsRequest, db: Session = Depends(get_db)):
    return apply_inbox_recommendations(db, payload.item_ids, payload.force_duplicate_ids)
