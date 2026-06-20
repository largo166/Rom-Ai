"""
检索引擎：SQLite FTS5/BM25 实现
替换 ilike，接入 RetrievalEngine 接口
零新依赖，利用 SQLite 内置 FTS5 扩展
"""
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.interfaces import RetrievalEngine

logger = logging.getLogger(__name__)

# FTS5 虚拟表名
FTS_TABLE = "knowledge_chunks_fts"

# 兼容已有安装：旧版 FTS 表没有 tags/path 字段，需要重建
_FTS_EXPECTED_COLUMNS = {"chunk_id", "heading", "content", "tags", "path"}


def _check_fts_schema(conn) -> bool:
    """检查现有 FTS5 表字段是否符合预期"""
    try:
        rows = conn.execute(text(f"PRAGMA table_info({FTS_TABLE})")).fetchall()
        if not rows:
            return False
        existing = {row[1] for row in rows}
        return _FTS_EXPECTED_COLUMNS.issubset(existing)
    except Exception:
        return False


def init_fts5(engine):
    """
    初始化 FTS5 虚拟表（如不存在则创建）
    在数据库初始化后调用
    """
    with engine.connect() as conn:
        # 如果表存在但字段不匹配，先删除重建
        table_exists = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
            ),
            {"name": FTS_TABLE},
        ).fetchone()

        if table_exists and not _check_fts_schema(conn):
            logger.warning("FTS5 table schema mismatch, dropping and recreating")
            conn.execute(text(f"DROP TABLE {FTS_TABLE}"))
            table_exists = None

        if not table_exists:
            # 创建 FTS5 外部内容表
            # chunk_id 存 knowledge_chunks.id（字符串），UNINDEXED 避免被分词
            # heading/content/tags/path 参与检索，使用 unicode61 tokenizer 支持中文
            conn.execute(text(f"""
                CREATE VIRTUAL TABLE {FTS_TABLE} USING fts5(
                    chunk_id UNINDEXED,
                    heading,
                    content,
                    tags,
                    path,
                    tokenize='unicode61'
                )
            """))
        conn.commit()
    logger.info("FTS5 virtual table initialized")


def rebuild_fts_index(engine):
    """
    重建 FTS5 索引（从 knowledge_chunks 表同步数据）
    """
    init_fts5(engine)
    with engine.connect() as conn:
        conn.execute(text(f"DELETE FROM {FTS_TABLE}"))
        conn.execute(text(f"""
            INSERT INTO {FTS_TABLE}(chunk_id, heading, content, tags, path)
            SELECT id, COALESCE(heading, ''), COALESCE(content, ''), COALESCE(tags, ''), COALESCE(path, '')
            FROM knowledge_chunks
        """))
        conn.commit()
    logger.info("FTS5 index rebuilt")


def sync_chunk_to_fts(engine, chunk_id: str, heading: str, content: str, tags: str, path: str = ""):
    """单条同步到 FTS 索引（新增/更新时调用）"""
    init_fts5(engine)
    with engine.connect() as conn:
        conn.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE chunk_id = :id"),
            {"id": chunk_id},
        )
        conn.execute(
            text(f"""
                INSERT INTO {FTS_TABLE}(chunk_id, heading, content, tags, path)
                VALUES (:id, :heading, :content, :tags, :path)
            """),
            {
                "id": chunk_id,
                "heading": heading or "",
                "content": content or "",
                "tags": tags or "",
                "path": path or "",
            },
        )
        conn.commit()


def sanitize_fts_query(query: str) -> str:
    """清理查询词，移除 FTS5 特殊语法字符，分词后用 OR 连接"""
    if not query:
        return ""
    # 移除 FTS5 操作符和引号
    cleaned = re.sub(r'["\*\(\)\{\}\[\]^~]', ' ', query)
    # 分词后用空格连接（隐式 AND）或 OR 连接（更宽松）
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return ""
    # 用 OR 连接多个词（更宽松的匹配）
    return " OR ".join(tokens[:12])


def search_fts5(
    engine,
    query: str,
    top_k: int = 10,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    FTS5 全文检索 + BM25 排序
    返回: [{chunk_id, content, score, title, tags, file_id, path}, ...]
    """
    if not query or not query.strip():
        return []

    clean_query = sanitize_fts_query(query)
    if not clean_query:
        return []

    init_fts5(engine)

    with engine.connect() as conn:
        # BM25 排序检索；bm25() 返回负值，绝对值越大相关性越高
        result = conn.execute(
            text(f"""
                SELECT
                    kc.id as chunk_id,
                    kc.content,
                    kc.heading,
                    kc.tags,
                    kc.path,
                    kc.file_id,
                    bm25({FTS_TABLE}) as score
                FROM {FTS_TABLE} fts
                JOIN knowledge_chunks kc ON kc.id = fts.chunk_id
                WHERE {FTS_TABLE} MATCH :query
                ORDER BY bm25({FTS_TABLE})
                LIMIT :top_k
            """),
            {"query": clean_query, "top_k": top_k},
        )
        rows = result.fetchall()

    results = []
    for row in rows:
        score = row[6]
        try:
            score = abs(float(score)) if score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        results.append({
            "chunk_id": row[0],
            "content": row[1] or "",
            "title": row[2] or row[4] or "",  # 优先用 heading，否则 path
            "tags": row[3] or "",
            "path": row[4] or "",
            "file_id": row[5],
            "score": score,
        })

    return results


def _fallback_search(engine, query: str, top_k: int) -> List[Dict[str, Any]]:
    """降级搜索（ilike），在 FTS5 不可用时使用"""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, content, heading, tags, path, file_id
                FROM knowledge_chunks
                WHERE content LIKE :q OR heading LIKE :q OR tags LIKE :q OR path LIKE :q
                LIMIT :top_k
            """),
            {"q": f"%{query}%", "top_k": top_k},
        )
        rows = result.fetchall()

    return [
        {
            "chunk_id": r[0],
            "content": r[1] or "",
            "title": r[2] or r[4] or "",
            "tags": r[3] or "",
            "path": r[4] or "",
            "file_id": r[5],
            "score": 0.5,
        }
        for r in rows
    ]


class FTS5RetrievalEngine(RetrievalEngine):
    """
    FTS5 实现的 RetrievalEngine
    替换 interfaces.py 中的 SqliteRetrievalEngine 占位
    """

    def __init__(self, engine):
        self.engine = engine
        try:
            init_fts5(engine)
        except Exception as e:
            logger.warning("FTS5 init failed (may already exist): %s", e)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """FTS5 全文检索"""
        try:
            return search_fts5(self.engine, query, top_k, filters)
        except Exception as e:
            logger.error("FTS5 search failed: %s", e)
            return _fallback_search(self.engine, query, top_k)

    def index(self, chunks: List[Dict[str, Any]]) -> int:
        """索引 chunks 到 FTS5"""
        count = 0
        for chunk in chunks:
            try:
                sync_chunk_to_fts(
                    self.engine,
                    str(chunk.get("id", "")),
                    chunk.get("heading", ""),
                    chunk.get("content", ""),
                    chunk.get("tags", ""),
                    chunk.get("path", ""),
                )
                count += 1
            except Exception as e:
                logger.error("Index chunk %s failed: %s", chunk.get("id"), e)
        return count

    def rebuild(self) -> None:
        """重建完整索引"""
        rebuild_fts_index(self.engine)
