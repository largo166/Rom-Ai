import unittest
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.database import Base
from app.services import (
    apply_inbox_items,
    apply_inbox_recommendations,
    build_inbox_batch_advice,
    classify_inbox_item,
    create_inbox_item_from_path,
    delete_inbox_items,
    recommend_inbox_item,
    run_inbox_scan_with_progress,
    search_knowledge,
)
from app.routes.inbox import scan_inbox


class InboxWorkflowTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_classify_matches_existing_project_from_filename(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                project = models.Project(name="杭州萧山湘北强排", city="杭州", project_type="住宅", phase="强排")
                db.add(project)
                db.commit()
                source = Path(tmp) / "杭州萧山湘北强排_启动会纪要_20260610.md"
                source.write_text("会议纪要\n参会人确认先复核日照和消防登高面。", encoding="utf-8")

                item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                classify_inbox_item(db, item)

                self.assertEqual(item.project_id, project.id)
                self.assertEqual(item.status, "待确认")
                self.assertEqual(item.material_type, "会议资料")
                self.assertTrue(item.suggest_todo)
                self.assertTrue(item.suggested_filename.endswith(".md"))
            finally:
                db.close()

    def test_classify_suggests_new_project_when_no_existing_project_matches(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                source = Path(tmp) / "保利市庄_规划条件_20260610.txt"
                source.write_text("规划条件包含容积率、退界和消防要求。", encoding="utf-8")

                item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                classify_inbox_item(db, item)

                self.assertEqual(item.project_id, "")
                self.assertEqual(item.status, "未归属项目")
                self.assertIn("保利市庄", item.suggested_project_name)
                self.assertEqual(item.material_type, "技术条件")
                self.assertTrue(item.suggest_knowledge)
            finally:
                db.close()

    def test_apply_can_create_project_archive_file_and_index_knowledge(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                source = Path(tmp) / "保利市庄_日照退界_20260610.md"
                source.write_text("# 日照退界\n本项目需要复核日照、退界和消防登高面。", encoding="utf-8")
                item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                classify_inbox_item(db, item)

                result = apply_inbox_items(
                    db,
                    [item.id],
                    project_payload=schemas.ProjectCreate(name="保利市庄", city="石家庄", project_type="住宅", phase="强排"),
                    enter_knowledge=True,
                    archive_root=Path(tmp) / "projects",
                )

                self.assertEqual(len(result["files"]), 1)
                self.assertEqual(result["project"].name, "保利市庄")
                self.assertEqual(result["items"][0].status, "已进入知识库")
                self.assertTrue(Path(result["files"][0].filepath).exists())
                self.assertEqual(result["files"][0].filename, result["items"][0].final_filename)
                chunks = search_knowledge(db, "保利市庄 日照 退界", limit=5)
                self.assertTrue(any("消防登高面" in chunk.content for chunk in chunks))
            finally:
                db.close()

    def test_delete_inbox_item_removes_temp_copy_but_keeps_source_file(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                source = Path(tmp) / "市庄_任务书.md"
                source.write_text("设计任务书", encoding="utf-8")
                item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                temp_path = Path(item.temp_path)

                deleted = delete_inbox_items(db, [item.id])

                self.assertEqual(deleted, 1)
                self.assertTrue(source.exists())
                self.assertFalse(temp_path.exists())
                self.assertIsNone(db.get(models.InboxItem, item.id))
            finally:
                db.close()

    def test_recommend_marks_duplicate_project_file_by_file_hash(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                project = models.Project(name="湘北强排", city="杭州", phase="强排")
                db.add(project)
                db.commit()
                archived = Path(tmp) / "archived.md"
                archived.write_text("同一个文件内容", encoding="utf-8")
                project_file = models.ProjectFile(
                    project_id=project.id,
                    filename="archived.md",
                    filepath=str(archived),
                    filetype="md",
                    filesize=archived.stat().st_size,
                )
                db.add(project_file)
                db.commit()
                source = Path(tmp) / "湘北强排_启动会纪要.md"
                source.write_text("同一个文件内容", encoding="utf-8")

                item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                classify_inbox_item(db, item)
                recommend_inbox_item(db, item)

                self.assertEqual(item.status, "重复文件")
                self.assertEqual(item.archive_group, "重复文件")
                self.assertEqual(item.duplicate_scope, "project")
                self.assertEqual(item.duplicate_project_file_id, project_file.id)
                self.assertEqual(item.recommended_action, "重复跳过")
                self.assertFalse(item.suggest_knowledge)
            finally:
                db.close()

    def test_recommend_marks_duplicate_knowledge_file_by_file_hash(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                knowledge = Path(tmp) / "规划条件.md"
                knowledge.write_text("容积率退界消防", encoding="utf-8")
                knowledge_file = models.KnowledgeFile(
                    filename="规划条件.md",
                    filepath=str(knowledge),
                    filetype="md",
                    filesize=knowledge.stat().st_size,
                )
                db.add(knowledge_file)
                db.commit()
                source = Path(tmp) / "新项目_规划条件.md"
                source.write_text("容积率退界消防", encoding="utf-8")

                item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                classify_inbox_item(db, item)
                recommend_inbox_item(db, item)

                self.assertEqual(item.status, "重复文件")
                self.assertEqual(item.duplicate_scope, "knowledge")
                self.assertEqual(item.duplicate_knowledge_file_id, knowledge_file.id)
            finally:
                db.close()

    def test_recommend_knowledge_defaults_by_material_type(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                tech = Path(tmp) / "市庄_规划条件.md"
                tech.write_text("规划条件包含容积率、退界、消防。", encoding="utf-8")
                tech_item = create_inbox_item_from_path(db, tech, Path(tmp) / "inbox")
                classify_inbox_item(db, tech_item)
                recommend_inbox_item(db, tech_item)

                archive = Path(tmp) / "模型文件.zip"
                archive.write_text("zip", encoding="utf-8")
                archive_item = create_inbox_item_from_path(db, archive, Path(tmp) / "inbox")
                classify_inbox_item(db, archive_item)
                recommend_inbox_item(db, archive_item)

                self.assertTrue(tech_item.suggest_knowledge)
                self.assertEqual(tech_item.recommended_action, "创建新项目")
                self.assertIn("跨项目复用", tech_item.recommend_knowledge_reason)
                self.assertFalse(archive_item.suggest_knowledge)
                self.assertEqual(archive_item.recommend_knowledge_reason, "压缩包与杂项默认只做项目资产记录。")
            finally:
                db.close()

    def test_apply_recommendations_skips_duplicate_by_default(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                project = models.Project(name="湘北强排")
                db.add(project)
                db.commit()
                existing = Path(tmp) / "existing.md"
                existing.write_text("重复内容", encoding="utf-8")
                db.add(models.ProjectFile(project_id=project.id, filename="existing.md", filepath=str(existing), filetype="md", filesize=existing.stat().st_size))
                db.commit()

                duplicate_source = Path(tmp) / "湘北强排_启动会纪要.md"
                duplicate_source.write_text("重复内容", encoding="utf-8")
                duplicate = create_inbox_item_from_path(db, duplicate_source, Path(tmp) / "inbox")
                classify_inbox_item(db, duplicate)
                recommend_inbox_item(db, duplicate)

                fresh_source = Path(tmp) / "湘北强排_规划条件.md"
                fresh_source.write_text("规划条件包含容积率、退界和消防。", encoding="utf-8")
                fresh = create_inbox_item_from_path(db, fresh_source, Path(tmp) / "inbox")
                classify_inbox_item(db, fresh)
                recommend_inbox_item(db, fresh)

                result = apply_inbox_recommendations(db, [duplicate.id, fresh.id], archive_root=Path(tmp) / "projects")

                self.assertEqual(result["skipped_count"], 1)
                self.assertEqual(len(result["files"]), 1)
                self.assertEqual(db.get(models.InboxItem, duplicate.id).status, "重复文件")
                self.assertIn(db.get(models.InboxItem, fresh.id).status, {"已归档", "已进入知识库"})
            finally:
                db.close()

    def test_manual_scan_without_days_limit_imports_old_files(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                source = Path(tmp) / "旧资料_规划条件.md"
                source.write_text("规划条件包含容积率、退界和消防。", encoding="utf-8")
                old_time = time.time() - 60 * 60 * 24 * 60
                os.utime(source, (old_time, old_time))

                imported = scan_inbox(schemas.InboxScanRequest(path=tmp, source_label="测试目录", days=0), db)

                self.assertEqual(len(imported), 1)
                self.assertEqual(imported[0].original_filename, "旧资料_规划条件.md")
            finally:
                db.close()

    def test_scan_progress_reports_steps_and_import_count(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                source = Path(tmp) / "保利市庄_规划条件_20260610.md"
                source.write_text("规划条件包含容积率、退界和消防。", encoding="utf-8")
                progress = {"status": "running"}

                result = run_inbox_scan_with_progress(db, Path(tmp), "测试目录", 0, progress)

                self.assertEqual(result["imported_count"], 1)
                self.assertEqual(progress["status"], "succeeded")
                self.assertEqual(progress["imported_files"], 1)
                self.assertEqual(progress["step"], "完成")
                self.assertEqual(progress["processed"], progress["total_candidates"])
                self.assertIn("batch_advice", result)
            finally:
                db.close()

    def test_batch_advice_recommends_clear_files_and_skips_duplicates(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                project = models.Project(name="杭州萧山湘北强排", city="杭州", project_type="住宅", phase="强排")
                db.add(project)
                db.commit()

                existing = Path(tmp) / "existing.md"
                existing.write_text("重复内容", encoding="utf-8")
                db.add(models.ProjectFile(project_id=project.id, filename="existing.md", filepath=str(existing), filetype="md", filesize=existing.stat().st_size))
                db.commit()

                clear_source = Path(tmp) / "杭州萧山湘北强排_规划条件_20260610.md"
                clear_source.write_text("规划条件包含容积率、退界和消防。", encoding="utf-8")
                clear_item = create_inbox_item_from_path(db, clear_source, Path(tmp) / "inbox")
                classify_inbox_item(db, clear_item)

                duplicate_source = Path(tmp) / "杭州萧山湘北强排_重复资料.md"
                duplicate_source.write_text("重复内容", encoding="utf-8")
                duplicate_item = create_inbox_item_from_path(db, duplicate_source, Path(tmp) / "inbox")
                classify_inbox_item(db, duplicate_item)

                advice = build_inbox_batch_advice(db, [])

                self.assertEqual(advice["total_files"], 2)
                self.assertIn(clear_item.id, advice["recommended_item_ids"])
                self.assertNotIn(duplicate_item.id, advice["recommended_item_ids"])
                self.assertEqual(advice["action_counts"]["归档文件"], 1)
                self.assertEqual(advice["action_counts"]["跳过重复"], 1)
                self.assertEqual(advice["action_counts"]["入知识库"], 1)
                self.assertTrue(advice["markdown"])
            finally:
                db.close()

    def test_batch_advice_groups_unassigned_as_new_project_candidate(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                source = Path(tmp) / "保利市庄_启动会纪要_20260610.md"
                source.write_text("会议纪要\n参会人讨论报规节点和设计任务。", encoding="utf-8")
                item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                classify_inbox_item(db, item)

                advice = build_inbox_batch_advice(db, [item.id])

                self.assertIn(item.id, advice["recommended_item_ids"])
                self.assertEqual(advice["action_counts"]["创建项目"], 1)
                self.assertTrue(any(group["project_name"] == item.suggested_project_name for group in advice["project_groups"]))
                self.assertIn("建议创建", advice["markdown"])
            finally:
                db.close()

    def test_batch_advice_merges_zhensanjie_files_into_one_project(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                samples = [
                    ("20260114石家庄振三街项目汇报.md", "石家庄市振三街地块项目 概念方案设计。容积率与消防要求见图纸。"),
                    ("20260103-石家庄市桥西区振三街地块方案设计.md", "石家庄 桥西区振三街地块 方案设计，用地条件与产品排布。"),
                    ("260202-附件2：振三街项目定位报告(配套+竞品）(1).md", "振三街项目定位报告，竞品定位结论、配套分析与客户敏感点。"),
                    ("20260115石家庄市振三街地块项目0115.md", "石家庄市振三街地块项目 总平方案，容积率2.20，配套面积。"),
                    ("20260111石家庄振三街项目总图及户型.md", "振三街项目总图及户型，楼栋排布、户型配比和总图方案。"),
                    ("20260118-石家庄振三街项目汇报-集.md", "石家庄市振三街地块项目 概念方案设计 汇报合集。"),
                ]
                item_ids = []
                for filename, content in samples:
                    source = Path(tmp) / filename
                    source.write_text(content, encoding="utf-8")
                    item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                    classify_inbox_item(db, item)
                    item_ids.append(item.id)

                advice = build_inbox_batch_advice(db, item_ids)

                self.assertEqual(advice["action_counts"]["创建项目"], 1)
                self.assertEqual(len(advice["project_groups"]), 1)
                self.assertEqual(advice["project_groups"][0]["project_name"], "石家庄市振三街地块项目")
                self.assertEqual(advice["project_groups"][0]["file_count"], 6)
                self.assertLess(advice["action_counts"]["入知识库"], 6)
                self.assertTrue(any("竞品" in candidate["reason"] for candidate in advice["knowledge_candidates"]))
            finally:
                db.close()

    def test_batch_advice_merges_xiangbei_aliases_into_one_project(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                samples = [
                    ("杭州湘北地块项目_规划条件_20260610.md", "杭州湘北地块项目 规划条件，容积率、退界和消防要求。"),
                    ("湘北地块强排方案.pdf", "湘北地块 强排方案，总图排布和日照复核。"),
                    ("杭州萧山湘北项目总图及户型.pptx", "杭州萧山湘北项目 总图及户型资料。"),
                    ("湘北地块启动会纪要.md", "湘北地块启动会纪要，讨论报规节点和设计任务。"),
                ]
                item_ids = []
                for filename, content in samples:
                    source = Path(tmp) / filename
                    source.write_text(content, encoding="utf-8")
                    item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                    classify_inbox_item(db, item)
                    item_ids.append(item.id)

                advice = build_inbox_batch_advice(db, item_ids)

                self.assertEqual(advice["action_counts"]["创建项目"], 1)
                self.assertEqual(len(advice["project_groups"]), 1)
                self.assertEqual(advice["project_groups"][0]["project_name"], "杭州湘北地块项目")
                self.assertEqual(advice["project_groups"][0]["file_count"], 4)
            finally:
                db.close()

    def test_apply_recommendations_creates_one_project_for_merged_batch(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                filenames = [
                    "20260114石家庄振三街项目汇报.md",
                    "20260111石家庄振三街项目总图及户型.md",
                    "20260115石家庄市振三街地块项目0115.md",
                ]
                item_ids = []
                for filename in filenames:
                    source = Path(tmp) / filename
                    source.write_text("石家庄市振三街地块项目 概念方案设计，总图和户型资料。", encoding="utf-8")
                    item = create_inbox_item_from_path(db, source, Path(tmp) / "inbox")
                    classify_inbox_item(db, item)
                    item_ids.append(item.id)

                result = apply_inbox_recommendations(db, item_ids, archive_root=Path(tmp) / "projects")

                self.assertEqual(result["created_project_count"], 1)
                self.assertEqual(len(result["files"]), 3)
                projects = list(db.query(models.Project).all())
                self.assertEqual(len(projects), 1)
                self.assertEqual(projects[0].name, "石家庄市振三街地块项目")
                self.assertEqual({file.project_id for file in result["files"]}, {projects[0].id})
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
