"""知识增强推荐引擎 — 在工作触发点主动推荐相关知识。"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.orm import Session

from app.json_safety import safe_json_parse
from app.utils import utc_now_iso

logger = logging.getLogger(__name__)

# 有效触发点列表
VALID_TRIGGERS = {"analysis", "okf_refresh", "meeting", "review", "ppt", "archive"}


@dataclass
class RecommendationItem:
    title: str
    content_preview: str       # 前 200 字
    source_type: str           # "knowledge_item" / "skill_card" / "meeting" / "inbox_item"
    source_id: str
    source_path: Optional[str]
    hit_reason: str            # "与项目类型匹配" / "含相似甲方表达" 等
    relevance_score: float


@dataclass
class RecommendationResult:
    trigger: str
    recommendations: List[RecommendationItem] = field(default_factory=list)
    query_keywords: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now_iso)


# ─────────────────────────── 内部工具函数 ───────────────────────────


def _extract_project_keywords(project) -> List[str]:
    """从 Project 模型提取关键词列表。"""
    keywords: List[str] = []
    for attr in ("project_type", "city", "phase", "name"):
        val = getattr(project, attr, None)
        if val and isinstance(val, str) and val.strip():
            keywords.append(val.strip())

    # 从 client_demands 中提取前几个词
    demands = getattr(project, "client_demands", None) or ""
    if demands:
        parts = re.split(r"[，,、；;\s]+", demands.strip())
        keywords.extend(p.strip() for p in parts[:3] if p.strip())

    return keywords


def _fts_search(db: Session, query: str, limit: int) -> List[dict]:
    """使用 search_knowledge 进行 FTS5 检索，返回标准化 dict 列表。"""
    if not query or not query.strip():
        return []
    try:
        from app.services.knowledge import search_knowledge
        from app.database import engine as db_engine
        from app.retrieval import search_fts5

        # 优先使用底层 search_fts5（有 BM25 分数）
        try:
            results = search_fts5(db_engine, query, top_k=limit)
            return results
        except Exception:
            pass

        # 降级到 search_knowledge ORM 接口
        chunks = search_knowledge(db, query, limit=limit)
        return [
            {
                "chunk_id": c.id,
                "content": c.content or "",
                "title": c.heading or c.path or "",
                "tags": c.tags or "",
                "path": c.path or "",
                "file_id": c.file_id,
                "score": 0.5,
            }
            for c in chunks
        ]
    except Exception as e:
        logger.warning("知识检索失败（非致命）: %s", e)
        return []


def _build_items(
    raw_results: List[dict],
    hit_reason: str,
    limit: int,
    type_weight: float = 1.0,
) -> List[RecommendationItem]:
    """将 FTS5 原始结果转为 RecommendationItem 列表。"""
    items = []
    for r in raw_results[:limit]:
        score = float(r.get("score") or 0.0) * type_weight
        content = r.get("content") or ""
        items.append(
            RecommendationItem(
                title=r.get("title") or r.get("path") or "（无标题）",
                content_preview=content[:200],
                source_type="knowledge_item",
                source_id=str(r.get("chunk_id") or ""),
                source_path=r.get("path") or None,
                hit_reason=hit_reason,
                relevance_score=round(score, 4),
            )
        )
    # 按相关性降序
    items.sort(key=lambda x: x.relevance_score, reverse=True)
    return items


def _multi_query_search(db: Session, queries: List[str], limit: int) -> List[dict]:
    """对多个 query 分别检索，合并去重结果。"""
    seen_ids: set = set()
    combined: List[dict] = []
    per_query_limit = max(limit, 5)
    for q in queries:
        results = _fts_search(db, q, per_query_limit)
        for r in results:
            cid = r.get("chunk_id")
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                combined.append(r)
    return combined


# ─────────────────────────── 6 个触发点函数 ───────────────────────────


def get_analysis_recommendations(
    db: Session, project_id: str, limit: int = 5
) -> RecommendationResult:
    """启动分析时：推荐类似项目经验、历史风险、同类型任务书。"""
    from app import models
    from sqlalchemy import select

    project = db.scalar(select(models.Project).where(models.Project.id == project_id))
    if not project:
        return RecommendationResult(trigger="analysis")

    keywords = _extract_project_keywords(project)
    project_type = (project.project_type or "").strip()
    city = (project.city or "").strip()

    queries = []
    if project_type:
        queries.append(f"{project_type} 风险")
        queries.append(f"{project_type} 启动分析")
    if city:
        queries.append(f"{city} 项目")
    if not queries:
        queries = ["项目启动 风险 分析"]

    raw = _multi_query_search(db, queries, limit * 2)
    hit_reason = "与项目类型[" + (project_type or "未知") + "]匹配"
    items = _build_items(raw, hit_reason, limit)

    return RecommendationResult(
        trigger="analysis",
        recommendations=items[:limit],
        query_keywords=keywords,
    )


def get_okf_refresh_recommendations(
    db: Session, project_id: str, card_type: str = "", limit: int = 5
) -> RecommendationResult:
    """OKF 刷新时：推荐缺失上下文、可补案例、相关方法模板。"""
    from app import models
    from sqlalchemy import select

    project = db.scalar(select(models.Project).where(models.Project.id == project_id))
    if not project:
        return RecommendationResult(trigger="okf_refresh")

    keywords = _extract_project_keywords(project)
    project_type = (project.project_type or "").strip()
    ct = (card_type or "").strip()

    queries = []
    if ct:
        queries.append(f"{ct} 模板")
        queries.append(f"{ct} 方法")
    if project_type:
        queries.append(f"{project_type} 上下文")
        queries.append(f"{project_type} 案例")
    if not queries:
        queries = ["上下文补充 模板"]

    raw = _multi_query_search(db, queries, limit * 2)
    hit_reason = "卡片类型[" + (ct or "通用") + "]相关模板"
    items = _build_items(raw, hit_reason, limit)

    return RecommendationResult(
        trigger="okf_refresh",
        recommendations=items[:limit],
        query_keywords=keywords + ([ct] if ct else []),
    )


def get_meeting_recommendations(
    db: Session, project_id: str, transcript_text: str = "", limit: int = 5
) -> RecommendationResult:
    """会议/沟通后：推荐类似甲方表达、历史转译。"""
    from app import models
    from sqlalchemy import select

    project = db.scalar(select(models.Project).where(models.Project.id == project_id))
    if not project:
        return RecommendationResult(trigger="meeting")

    keywords = _extract_project_keywords(project)

    # 从 transcript_text 中提取前 3 个有效短语（按标点分割）
    transcript_keywords: List[str] = []
    if transcript_text and transcript_text.strip():
        phrases = re.split(r"[，,。！？\n；;！!?]+", transcript_text.strip())
        for phrase in phrases:
            p = phrase.strip()
            if len(p) >= 4:
                transcript_keywords.append(p[:20])
            if len(transcript_keywords) >= 3:
                break

    queries = []
    for kw in transcript_keywords:
        queries.append(kw)
        queries.append(f"{kw} 甲方")
    # 兜底：项目类型 + 甲方
    project_type = (project.project_type or "").strip()
    if not queries:
        queries = [f"{project_type} 甲方诉求" if project_type else "甲方诉求 转译"]

    raw = _multi_query_search(db, queries, limit * 2)
    hit_reason = "含相似甲方表达或历史转译经验"
    items = _build_items(raw, hit_reason, limit)

    combined_kw = keywords + transcript_keywords
    return RecommendationResult(
        trigger="meeting",
        recommendations=items[:limit],
        query_keywords=combined_kw,
    )


def get_review_recommendations(
    db: Session, project_id: str, limit: int = 5
) -> RecommendationResult:
    """方案评审时：推荐风险清单、相似问题、设计追问。"""
    from app import models
    from sqlalchemy import select

    project = db.scalar(select(models.Project).where(models.Project.id == project_id))
    if not project:
        return RecommendationResult(trigger="review")

    keywords = _extract_project_keywords(project)
    project_type = (project.project_type or "").strip()

    queries = ["方案评审 风险"]
    if project_type:
        queries.append(f"{project_type} 评审要点")
        queries.append(f"{project_type} 设计问题")
    queries.append("设计追问 审查")

    raw = _multi_query_search(db, queries, limit * 2)
    hit_reason = "方案评审风险与[" + (project_type or "本项目") + "]相关"
    items = _build_items(raw, hit_reason, limit)

    return RecommendationResult(
        trigger="review",
        recommendations=items[:limit],
        query_keywords=keywords,
    )


def get_ppt_recommendations(
    db: Session, project_id: str, limit: int = 5
) -> RecommendationResult:
    """PPT 大纲时：推荐历史汇报结构、叙事模板。"""
    from app import models
    from sqlalchemy import select

    project = db.scalar(select(models.Project).where(models.Project.id == project_id))
    if not project:
        return RecommendationResult(trigger="ppt")

    keywords = _extract_project_keywords(project)
    project_type = (project.project_type or "").strip()

    queries = ["汇报结构", "PPT 大纲"]
    if project_type:
        queries.append(f"{project_type} 汇报")
        queries.append(f"{project_type} 演示")
    queries.append("叙事模板 汇报")

    raw = _multi_query_search(db, queries, limit * 2)
    hit_reason = "历史汇报结构与叙事模板参考"
    items = _build_items(raw, hit_reason, limit)

    return RecommendationResult(
        trigger="ppt",
        recommendations=items[:limit],
        query_keywords=keywords,
    )


def get_archive_recommendations(
    db: Session, project_id: str, file_names: List[str] = None, limit: int = 5
) -> RecommendationResult:
    """收件箱归档时：推荐新文件可能影响的判断/任务。"""
    from app import models
    from sqlalchemy import select

    project = db.scalar(select(models.Project).where(models.Project.id == project_id))
    if not project:
        return RecommendationResult(trigger="archive")

    file_names = file_names or []
    keywords = _extract_project_keywords(project)

    # 从文件名提取关键词（去除扩展名、日期数字）
    file_keywords: List[str] = []
    for fn in file_names[:5]:
        stem = re.sub(r"\.\w{2,5}$", "", fn)
        parts = re.split(r"[_\-\s\.]+", stem)
        for p in parts:
            p = p.strip()
            # 过滤纯数字/日期
            if p and not re.match(r"^\d+$", p) and len(p) >= 2:
                file_keywords.append(p)
                break

    queries = []
    for fk in file_keywords[:3]:
        queries.append(fk)
        queries.append(f"{fk} 分析")
    project_type = (project.project_type or "").strip()
    if not queries:
        queries = [f"{project_type} 归档" if project_type else "文档 归档 影响"]

    raw = _multi_query_search(db, queries, limit * 2)
    hit_reason = "新归档文件可能影响的相关分析或任务"
    items = _build_items(raw, hit_reason, limit)

    combined_kw = keywords + file_keywords
    return RecommendationResult(
        trigger="archive",
        recommendations=items[:limit],
        query_keywords=combined_kw,
    )


# ─────────────────────────── 统一调度入口 ───────────────────────────


def get_recommendations(
    db: Session,
    project_id: str,
    trigger: str,
    limit: int = 5,
    **kwargs,
) -> RecommendationResult:
    """统一推荐入口，根据 trigger 分派到对应函数。

    Args:
        db: SQLAlchemy Session
        project_id: 项目 ID
        trigger: 触发点类型，有效值：analysis / okf_refresh / meeting / review / ppt / archive
        limit: 最多返回条数（默认 5）
        **kwargs: 各触发点的额外参数：
            - meeting: transcript_text (str)
            - okf_refresh: card_type (str)
            - archive: file_names (list[str])

    Raises:
        ValueError: 当 trigger 不在 VALID_TRIGGERS 中时
    """
    if trigger not in VALID_TRIGGERS:
        raise ValueError(
            f"无效的触发点类型: '{trigger}'。有效值：{sorted(VALID_TRIGGERS)}"
        )

    dispatch = {
        "analysis": lambda: get_analysis_recommendations(db, project_id, limit=limit),
        "okf_refresh": lambda: get_okf_refresh_recommendations(
            db, project_id, card_type=kwargs.get("card_type", ""), limit=limit
        ),
        "meeting": lambda: get_meeting_recommendations(
            db, project_id, transcript_text=kwargs.get("transcript_text", ""), limit=limit
        ),
        "review": lambda: get_review_recommendations(db, project_id, limit=limit),
        "ppt": lambda: get_ppt_recommendations(db, project_id, limit=limit),
        "archive": lambda: get_archive_recommendations(
            db, project_id, file_names=kwargs.get("file_names", []), limit=limit
        ),
    }

    try:
        return dispatch[trigger]()
    except Exception as e:
        logger.error("get_recommendations 执行失败 trigger=%s: %s", trigger, e)
        return RecommendationResult(trigger=trigger)
