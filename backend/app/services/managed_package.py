"""Managed project material packages.

This service is the non-destructive intake path for local project folders:
the source folder is read-only, while ROM-AI creates its own managed copy,
Markdown summaries, manifest files, project file bindings, and knowledge
index records.
"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.core import SUPPORTED_KNOWLEDGE_EXTS, parse_document
from app.services.knowledge import index_knowledge_file, upsert_knowledge_markdown


def _safe_rel(path: Path, root: Path) -> Path:
    rel = path.relative_to(root)
    if any(part in {"", ".", ".."} or ":" in part for part in rel.parts):
        raise ValueError(f"不安全的相对路径：{rel}")
    return rel


def _project_root(project_id: str | None, package_id: str) -> Path:
    if project_id:
        return settings.upload_root_path / "projects" / project_id / "managed"
    return settings.upload_root_path / "managed-packages" / package_id


def _summary_markdown(
    *,
    project: models.Project | None,
    source_path: Path,
    managed_path: Path,
    rel_path: Path,
    parsed_text: str,
    status: str,
) -> str:
    project_name = project.name if project else "未绑定项目"
    city = project.city if project else ""
    excerpt = parsed_text.strip()[:2400] if parsed_text.strip() else "该文件已登记，当前类型暂不支持全文解析。"
    return "\n".join(
        [
            "---",
            "type: managed_material_summary",
            "source: rmo-ai",
            f'project_id: "{project.id if project else ""}"',
            f'title: "{source_path.name}"',
            f'city: "{city}"',
            f'updated: "{datetime.now().isoformat(timespec="seconds")}"',
            "---",
            "",
            f"# {source_path.name}",
            "",
            f"- 项目：{project_name}",
            f"- 原始路径：{source_path}",
            f"- 受管路径：{managed_path}",
            f"- 相对路径：{rel_path.as_posix()}",
            f"- 文件类型：{source_path.suffix.lower().lstrip('.') or 'unknown'}",
            f"- 解析状态：{status}",
            "",
            "## 摘要",
            "",
            excerpt,
        ]
    )


def build_managed_package(
    db: Session,
    *,
    source_dir: Path,
    project: models.Project | None = None,
    package_label: str = "",
    copy_files: bool = True,
) -> dict[str, Any]:
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"目录不存在：{source_dir}")

    package_id = project.id if project else datetime.now().strftime("%Y%m%d%H%M%S")
    package_root = _project_root(project.id if project else None, package_id)
    files_root = package_root / "files"
    summaries_root = package_root / "summaries"
    files_root.mkdir(parents=True, exist_ok=True)
    summaries_root.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    stats: Counter[str] = Counter()

    candidates = [path for path in source_dir.rglob("*") if path.is_file()]
    for source_path in candidates:
        ext = source_path.suffix.lower()
        if ext not in SUPPORTED_KNOWLEDGE_EXTS:
            skipped.append({"path": str(source_path), "reason": "unsupported_type"})
            continue
        rel = _safe_rel(source_path, source_dir)
        managed_path = files_root / rel
        managed_path.parent.mkdir(parents=True, exist_ok=True)
        if copy_files:
            shutil.copy2(source_path, managed_path)
        else:
            managed_path = source_path

        parsed_text, status = parse_document(managed_path)
        summary = _summary_markdown(
            project=project,
            source_path=source_path,
            managed_path=managed_path,
            rel_path=rel,
            parsed_text=parsed_text,
            status=status,
        )
        summary_path = summaries_root / f"{rel.as_posix().replace('/', '__')}.md"
        summary_path.write_text(summary, encoding="utf-8")

        display_file_path = (
            f"managed-package/{project.id if project else package_id}/files/{rel.as_posix()}"
        )
        display_summary_path = (
            f"managed-package/{project.id if project else package_id}/summaries/{summary_path.name}"
        )
        index_knowledge_file(db, managed_path, display_path=display_file_path)
        upsert_knowledge_markdown(
            db,
            display_summary_path,
            f"{source_path.stem} 资料摘要",
            summary,
            [
                "受管资料包",
                project.name if project else "未绑定项目",
                project.city if project else "",
                ext.lstrip("."),
            ],
        )

        if project:
            existing = db.scalar(
                select(models.ProjectFile).where(
                    models.ProjectFile.project_id == project.id,
                    models.ProjectFile.filepath == str(managed_path),
                )
            )
            if not existing:
                existing = models.ProjectFile(project_id=project.id, filepath=str(managed_path))
                db.add(existing)
                db.flush()
            existing.filename = source_path.name
            existing.filetype = ext.lstrip(".")
            existing.filesize = managed_path.stat().st_size
            existing.parsed_text = parsed_text[:200000]
            existing.parse_status = status

        record = {
            "original_path": str(source_path),
            "managed_path": str(managed_path),
            "summary_path": str(summary_path),
            "relative_path": rel.as_posix(),
            "filetype": ext.lstrip("."),
            "filesize": managed_path.stat().st_size,
            "parse_status": status,
            "indexed_path": display_file_path,
            "summary_indexed_path": display_summary_path,
        }
        records.append(record)
        stats["total_files"] += 1
        stats[ext.lstrip(".") or "other"] += 1

    manifest = {
        "type": "managed_project_material_package",
        "source": "rmo-ai",
        "package_label": package_label or source_dir.name,
        "source_dir": str(source_dir),
        "project_id": project.id if project else "",
        "project_name": project.name if project else "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "copy_files": copy_files,
        "stats": dict(stats),
        "files": records,
        "skipped": skipped,
    }
    (package_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (package_root / "original_refs.json").write_text(
        json.dumps(
            [{"original_path": item["original_path"], "managed_path": item["managed_path"]} for item in records],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    db.commit()
    return {
        "package_root": str(package_root),
        "manifest_path": str(package_root / "manifest.json"),
        "indexed_files": len(records),
        "skipped_files": skipped,
        "stats": dict(stats),
        "recent_files": records[:20],
    }
