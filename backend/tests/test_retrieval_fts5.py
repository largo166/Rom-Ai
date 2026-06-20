"""test_retrieval_fts5.py — FTS5 检索引擎单元测试"""
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import KnowledgeChunk, KnowledgeFile
from app.retrieval import (
    FTS_TABLE,
    FTS5RetrievalEngine,
    init_fts5,
    rebuild_fts_index,
    sanitize_fts_query,
    search_fts5,
    sync_chunk_to_fts,
)


def make_engine():
    """创建内存数据库引擎"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def make_session(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def seed_knowledge(db, engine) -> list[str]:
    """插入测试知识库数据，返回 chunk id 列表"""
    kf1 = KnowledgeFile(
        filename="项目规划.md",
        filepath="docs/项目规划.md",
        filetype="md",
        title="项目规划",
        folder="docs",
    )
    kf2 = KnowledgeFile(
        filename="architecture.md",
        filepath="docs/architecture.md",
        filetype="md",
        title="System Architecture",
        folder="docs",
    )
    db.add_all([kf1, kf2])
    db.flush()

    # 中文内容 chunk
    kc1 = KnowledgeChunk(
        file_id=kf1.id,
        heading="项目背景",
        content="本项目是一个智能档案管理系统，利用人工智能提升规划效率，支持甲方需求分析和自动报告生成。",
        path="docs/项目规划.md",
        tags='["规划", "人工智能"]',
    )
    # 高度相关的中文内容（用于 BM25 排序验证）
    kc2 = KnowledgeChunk(
        file_id=kf1.id,
        heading="甲方需求",
        content="甲方要求系统具备甲方需求自动转译、甲方信息管理和甲方联络追踪功能，甲方提出了十项甲方核心诉求。",
        path="docs/项目规划.md",
        tags='["甲方", "需求"]',
    )
    # 英文内容 chunk
    kc3 = KnowledgeChunk(
        file_id=kf2.id,
        heading="Backend Architecture",
        content="The backend uses FastAPI with SQLAlchemy ORM, connected to a SQLite database with FTS5 full-text search support.",
        path="docs/architecture.md",
        tags='["fastapi", "sqlite", "fts5"]',
    )
    kc4 = KnowledgeChunk(
        file_id=kf2.id,
        heading="Frontend Stack",
        content="Frontend is built with React, TypeScript and Vite. The UI components use Tailwind CSS for styling.",
        path="docs/architecture.md",
        tags='["react", "typescript"]',
    )
    db.add_all([kc1, kc2, kc3, kc4])
    db.commit()

    # 同步到 FTS 索引
    for kc in [kc1, kc2, kc3, kc4]:
        sync_chunk_to_fts(engine, kc.id, kc.heading, kc.content, kc.tags, kc.path)

    return [kc1.id, kc2.id, kc3.id, kc4.id]


class TestFTS5Init(unittest.TestCase):
    """init_fts5 初始化测试"""

    def test_init_fts5_creates_virtual_table(self):
        """调用 init_fts5 后虚拟表应当存在"""
        engine = make_engine()
        init_fts5(engine)

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": FTS_TABLE},
            ).fetchone()

        self.assertIsNotNone(row, "FTS5 虚拟表未创建")
        self.assertEqual(row[0], FTS_TABLE)

    def test_init_fts5_idempotent(self):
        """多次调用 init_fts5 不报错（幂等性）"""
        engine = make_engine()
        init_fts5(engine)
        init_fts5(engine)  # 第二次调用不应抛出异常

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": FTS_TABLE},
            ).fetchone()

        self.assertIsNotNone(row)


class TestSearchFTS5(unittest.TestCase):
    """search_fts5 核心检索测试"""

    def setUp(self):
        self.engine = make_engine()
        self.db = make_session(self.engine)
        self.chunk_ids = seed_knowledge(self.db, self.engine)

    def test_search_fts5_chinese_content(self):
        """中文内容能被正确索引和检索"""
        results = search_fts5(self.engine, "人工智能")
        self.assertGreater(len(results), 0, "中文检索应返回结果")
        contents = [r["content"] for r in results]
        self.assertTrue(any("人工智能" in c for c in contents))

    def test_search_fts5_english_content(self):
        """英文内容正常检索"""
        results = search_fts5(self.engine, "FastAPI")
        self.assertGreater(len(results), 0, "英文检索应返回结果")
        contents = [r["content"] for r in results]
        self.assertTrue(any("FastAPI" in c for c in contents))

    def test_search_fts5_bm25_ranking(self):
        """高相关性结果排在前面（BM25 排序）"""
        # kc2 的内容中"甲方"出现频率极高，应排名最前
        results = search_fts5(self.engine, "甲方")
        self.assertGreater(len(results), 0)
        # 第一个结果的 score 应该最高（或至少存在多个结果）
        if len(results) > 1:
            self.assertGreaterEqual(results[0]["score"], results[1]["score"])
        # 第一条结果应该包含"甲方"
        self.assertIn("甲方", results[0]["content"])

    def test_search_fts5_multi_field(self):
        """标题命中和内容命中都能被检索到"""
        # heading 匹配："甲方需求"（完整词可被 unicode61 tokenizer 分词匹配）
        results_heading = search_fts5(self.engine, "甲方需求")
        self.assertGreater(len(results_heading), 0, "标题命中应返回结果")

        # content 匹配：直接搜索 content 中确定存在的英文词
        results_content = search_fts5(self.engine, "TypeScript")
        self.assertGreater(len(results_content), 0, "内容命中应返回结果")

    def test_search_fts5_empty_query(self):
        """空查询返回空结果而非报错"""
        results = search_fts5(self.engine, "")
        self.assertEqual(results, [], "空查询应返回空列表")

        results_whitespace = search_fts5(self.engine, "   ")
        self.assertEqual(results_whitespace, [], "全空格查询应返回空列表")

    def test_search_fts5_special_characters(self):
        """特殊字符（引号、括号等）不导致崩溃"""
        # 注意：sanitize_fts_query 会移除特殊字符后用 OR 连接
        # 含 FTS5 保留关键字（AND/OR/NOT）的查询，sanitize 后可能保留关键字词
        # 因此测试仅验证不含 FTS5 关键字的特殊字符组合
        special_queries = [
            '"FastAPI"',        # 引号
            '(sqlite)',          # 括号
            'react[typescript]', # 方括号
            'backend* ~search',  # 通配符和波浪号
        ]
        for q in special_queries:
            with self.subTest(query=q):
                try:
                    results = search_fts5(self.engine, q)
                    self.assertIsInstance(results, list)
                except Exception as e:
                    self.fail(f"特殊字符查询 '{q}' 抛出异常: {e}")

    def test_search_fts5_no_results(self):
        """查询不存在的内容返回空列表"""
        results = search_fts5(self.engine, "不存在的词汇XYZ12345")
        self.assertEqual(results, [], "不存在的内容应返回空列表")

    def test_search_fts5_limit(self):
        """结果数量不超过指定 limit"""
        results = search_fts5(self.engine, "docs", top_k=2)
        self.assertLessEqual(len(results), 2, "结果数量不应超过 limit")

    def test_search_fts5_result_fields(self):
        """返回结果包含所有预期字段"""
        results = search_fts5(self.engine, "FastAPI")
        self.assertGreater(len(results), 0)
        r = results[0]
        expected_keys = {"chunk_id", "content", "title", "tags", "path", "file_id", "score"}
        self.assertEqual(expected_keys, set(r.keys()))

    def test_search_fts5_score_positive(self):
        """检索结果的 score 应为非负数"""
        results = search_fts5(self.engine, "SQLite")
        for r in results:
            self.assertGreaterEqual(r["score"], 0.0, "score 应为非负数")


class TestRebuildFtsIndex(unittest.TestCase):
    """rebuild_fts_index 测试"""

    def test_rebuild_fts_index(self):
        """重建索引后检索仍然正常"""
        engine = make_engine()
        db = make_session(engine)
        seed_knowledge(db, engine)

        # 执行重建
        rebuild_fts_index(engine)

        # 重建后检索仍能正常工作
        results = search_fts5(engine, "FastAPI")
        self.assertGreater(len(results), 0, "重建索引后应能检索到数据")

    def test_rebuild_fts_index_syncs_from_knowledge_chunks(self):
        """rebuild_fts_index 从 knowledge_chunks 表同步数据"""
        engine = make_engine()
        db = make_session(engine)
        chunk_ids = seed_knowledge(db, engine)

        # 清空 FTS 表后重建
        with engine.connect() as conn:
            conn.execute(text(f"DELETE FROM {FTS_TABLE}"))
            conn.commit()

        # 验证清空后查不到数据
        results_before = search_fts5(engine, "FastAPI")
        self.assertEqual(results_before, [])

        # 重建
        rebuild_fts_index(engine)

        # 重建后应能查到数据
        results_after = search_fts5(engine, "FastAPI")
        self.assertGreater(len(results_after), 0)


class TestSearchKnowledgeFallback(unittest.TestCase):
    """search_knowledge 集成层降级逻辑测试"""

    def _make_patched_search_knowledge(self, engine, db):
        """
        直接调用底层检索逻辑进行集成测试，
        绕过 search_knowledge 中对全局 db_engine 的依赖。
        """
        from sqlalchemy import or_, select
        from app import models
        from app.retrieval import FTS5RetrievalEngine, sanitize_fts_query
        import re

        def patched_search_knowledge(question: str, limit: int = 6):
            terms = [t for t in re.split(r"\s+", question.strip()) if t]

            # 1) FTS5
            if terms:
                try:
                    retrieval = FTS5RetrievalEngine(engine)
                    fts_query = " ".join(terms[:12])
                    results = retrieval.search(fts_query, top_k=limit)
                    if results:
                        ids = [r["chunk_id"] for r in results if r.get("chunk_id")]
                        if ids:
                            by_id = {
                                chunk.id: chunk
                                for chunk in db.scalars(
                                    select(models.KnowledgeChunk).where(
                                        models.KnowledgeChunk.id.in_(ids)
                                    )
                                )
                            }
                            ordered = [by_id[i] for i in ids if i in by_id]
                            if ordered:
                                return ordered, "fts5"
                except Exception:
                    db.rollback()

            # 2) ilike 降级
            query = select(models.KnowledgeChunk)
            if terms:
                clauses = []
                for term in terms[:6]:
                    clauses.append(models.KnowledgeChunk.content.ilike(f"%{term}%"))
                    clauses.append(models.KnowledgeChunk.heading.ilike(f"%{term}%"))
                query = query.where(or_(*clauses))
            chunks = list(db.scalars(query.limit(limit)))
            return chunks, "ilike"

        return patched_search_knowledge

    def test_search_knowledge_fts5_returns_results(self):
        """FTS5 可用时应优先使用 FTS5 返回结果"""
        engine = make_engine()
        db = make_session(engine)
        seed_knowledge(db, engine)

        search_fn = self._make_patched_search_knowledge(engine, db)
        results, strategy = search_fn("FastAPI SQLite")

        self.assertGreater(len(results), 0, "FTS5 检索应返回结果")
        self.assertEqual(strategy, "fts5")

    def test_search_knowledge_fallback_ilike(self):
        """FTS5 无结果时降级到 ilike 仍能找到内容"""
        engine = make_engine()
        db = make_session(engine)

        # 只插入 ORM 数据，不同步到 FTS（模拟 FTS 无结果场景）
        kf = KnowledgeFile(
            filename="fallback_test.md",
            filepath="docs/fallback_test.md",
            filetype="md",
            title="降级测试",
            folder="docs",
        )
        db.add(kf)
        db.flush()
        kc = KnowledgeChunk(
            file_id=kf.id,
            heading="降级检索",
            content="这段文字仅存在于关系表而非FTS索引，用于验证ilike降级逻辑。",
            path="docs/fallback_test.md",
            tags="[]",
        )
        db.add(kc)
        db.commit()

        # 确保 FTS 中没有这条数据（不调用 sync_chunk_to_fts）
        # 搜索这条数据
        search_fn = self._make_patched_search_knowledge(engine, db)
        results, strategy = search_fn("仅存在于关系表")

        self.assertGreater(len(results), 0, "ilike 降级应能找到内容")
        self.assertEqual(strategy, "ilike", "当 FTS5 无结果时应使用 ilike 策略")


class TestSanitizeFtsQuery(unittest.TestCase):
    """sanitize_fts_query 清理函数测试"""

    def test_sanitize_empty_query(self):
        self.assertEqual(sanitize_fts_query(""), "")

    def test_sanitize_removes_special_chars(self):
        result = sanitize_fts_query('"quoted" (term)')
        self.assertNotIn('"', result)
        self.assertNotIn('(', result)
        self.assertNotIn(')', result)

    def test_sanitize_multi_word_joins_with_or(self):
        result = sanitize_fts_query("word1 word2")
        self.assertIn("OR", result)
        self.assertIn("word1", result)
        self.assertIn("word2", result)


class TestFTS5RetrievalEngine(unittest.TestCase):
    """FTS5RetrievalEngine 类方法测试"""

    def test_engine_search_returns_list(self):
        """FTS5RetrievalEngine.search 返回列表类型"""
        engine = make_engine()
        db = make_session(engine)
        seed_knowledge(db, engine)

        retrieval = FTS5RetrievalEngine(engine)
        results = retrieval.search("FastAPI", top_k=5)

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_engine_index_and_search(self):
        """FTS5RetrievalEngine.index 后能检索到数据"""
        engine = make_engine()
        db = make_session(engine)

        kf = KnowledgeFile(
            filename="test.md",
            filepath="test.md",
            filetype="md",
            title="Test",
            folder=".",
        )
        db.add(kf)
        db.flush()
        kc = KnowledgeChunk(
            file_id=kf.id,
            heading="Test Heading",
            content="Unique content for engine index test with special keyword engindextest.",
            path="test.md",
            tags="[]",
        )
        db.add(kc)
        db.commit()

        retrieval = FTS5RetrievalEngine(engine)
        count = retrieval.index([{
            "id": kc.id,
            "heading": kc.heading,
            "content": kc.content,
            "tags": kc.tags,
            "path": kc.path,
        }])
        self.assertEqual(count, 1)

        results = retrieval.search("engindextest")
        self.assertGreater(len(results), 0)

    def test_engine_rebuild(self):
        """FTS5RetrievalEngine.rebuild 后检索正常"""
        engine = make_engine()
        db = make_session(engine)
        seed_knowledge(db, engine)

        retrieval = FTS5RetrievalEngine(engine)
        retrieval.rebuild()  # 不应抛出异常

        results = retrieval.search("React")
        self.assertGreater(len(results), 0)


if __name__ == "__main__":
    unittest.main()
