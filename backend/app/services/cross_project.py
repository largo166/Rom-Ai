"""Cross-project experience retrieval.

This module keeps reusable historical-project lookup separate from generic
knowledge search. It is intentionally source-first: every recommendation must
carry a source path and hit reason, otherwise it is not returned.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.knowledge import search_knowledge


TECHNICAL_REUSE_KEYWORDS = ["日照", "退距", "限高", "容积率", "消防", "报批", "周期", "甲方偏好"]


def _project_terms(project: models.Project) -> list[str]:
    terms = []
    for value in [project.city, project.project_type, project.phase, project.client_name, project.name]:
        if value and value.strip():
            terms.append(value.strip())
    terms.extend(TECHNICAL_REUSE_KEYWORDS)
    return terms


def _known_neighbor_projects(db: Session, project: models.Project) -> list[str]:
    if not (project.city or "").strip():
        return []
    rows = db.scalars(
        select(models.Project).where(
            models.Project.id != project.id,
            models.Project.city == project.city,
        )
    )
    return [row.name for row in rows if row.name]


def collect_cross_project_experience(
    db: Session,
    project: models.Project,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Return source-backed reusable experience for a project.

    The result is safe to inject into project analysis. It never invents owner
    preference, schedule, or technical advice: no retrieved source means no item.
    """
    terms = _project_terms(project)
    neighbor_names = _known_neighbor_projects(db, project)
    if neighbor_names:
        terms.extend(neighbor_names[:4])

    query = " ".join(term for term in terms if term)
    if not query.strip():
        return []

    chunks = search_knowledge(db, query, limit=limit * 2)
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        path = chunk.path or ""
        if not path or path in seen:
            continue
        # Prefer historical or neighboring material; avoid echoing only the current data-link.
        if project.id and f"/{project.id}/" in path.replace("\\", "/"):
            continue
        seen.add(path)
        matched = []
        content = f"{chunk.heading or ''}\n{chunk.content or ''}"
        for term in terms:
            if term and term in content:
                matched.append(term)
        if not matched:
            matched = [project.city or project.project_type or "项目经验"]
        refs.append(
            {
                "chunk_id": chunk.id,
                "source_file": Path(path).name,
                "source_path": path,
                "heading": chunk.heading,
                "quote": (chunk.content or "")[:520],
                "relevance_score": 0.82,
                "hit_reason": " / ".join(
                    [
                        reason
                        for reason in [
                            f"同城项目：{project.city}" if project.city else "",
                            f"同类型：{project.project_type}" if project.project_type else "",
                            "命中关键词：" + "、".join(matched[:5]),
                        ]
                        if reason
                    ]
                ),
            }
        )
        if len(refs) >= limit:
            break
    return refs
