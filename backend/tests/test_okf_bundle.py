import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.database import Base
from app.routes.projects import generate_okf_bundle, get_project_okf_bundle
from app.services import OKF_BUNDLE_FILES, generate_project_okf_bundle, search_knowledge


class OkfBundleTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_empty_project_generates_minimal_okf_bundle_and_indexes_it(self):
        with TemporaryDirectory() as tmp:
            original_upload_root = settings.upload_root
            settings.upload_root = tmp
            db = self.open_temp_db()
            try:
                project = models.Project(name="哈尔滨展示区", city="哈尔滨", project_type="展示区", phase="concept")
                db.add(project)
                db.commit()
                db.refresh(project)

                status = generate_project_okf_bundle(db, project)

                self.assertTrue(status["generated"])
                self.assertEqual([item["name"] for item in status["files"]], list(OKF_BUNDLE_FILES))
                root = Path(tmp) / "projects" / project.id / "okf"
                for name in OKF_BUNDLE_FILES:
                    path = root / name
                    self.assertTrue(path.exists(), name)
                    text = path.read_text(encoding="utf-8")
                    self.assertIn("okf_version: 0.1", text)
                    self.assertIn("type: project_context", text)
                    self.assertIn(f'project_id: "{project.id}"', text)
                    self.assertIn("updated:", text)

                chunks = search_knowledge(db, f"{project.name} AI代理上下文 哈尔滨 展示区", limit=10)
                self.assertTrue(chunks)
                self.assertTrue(any(f"project-okf/{project.id}/agent_context.md" in chunk.path for chunk in chunks))
            finally:
                db.close()
                settings.upload_root = original_upload_root

    def test_okf_bundle_includes_project_meetings_tasks_and_assets(self):
        with TemporaryDirectory() as tmp:
            original_upload_root = settings.upload_root
            settings.upload_root = tmp
            db = self.open_temp_db()
            try:
                source = Path(tmp) / "任务书.md"
                source.write_text("任务书内容", encoding="utf-8")
                project = models.Project(name="复合社区", city="杭州", project_type="社区中心", phase="前期")
                project.files = [
                    models.ProjectFile(
                        filename="任务书.md",
                        filepath=str(source),
                        filetype="md",
                        filesize=source.stat().st_size,
                        parsed_text="需要形成社区公共客厅和全天候灰空间。",
                        parse_status="parsed",
                    )
                ]
                project.tasks = [models.ProjectTask(task_name="复核首层开放界面", owner_role="方案主创", risk_level="高")]
                project.meetings = [
                    models.Meeting(
                        title="甲方沟通会",
                        summary="甲方强调公共性和昭示性。",
                        next_actions_json='[{"title":"补充灰空间案例","owner":"方案主创"}]',
                    )
                ]
                db.add(project)
                db.commit()
                db.refresh(project)

                generate_project_okf_bundle(db, project)
                root = Path(tmp) / "projects" / project.id / "okf"

                self.assertIn("甲方沟通会", (root / "meetings.md").read_text(encoding="utf-8"))
                self.assertIn("复核首层开放界面", (root / "agent_context.md").read_text(encoding="utf-8"))
                self.assertIn("任务书.md", (root / "assets.md").read_text(encoding="utf-8"))
            finally:
                db.close()
                settings.upload_root = original_upload_root

    def test_okf_bundle_routes_report_status_and_refresh_without_duplicate_index_files(self):
        with TemporaryDirectory() as tmp:
            original_upload_root = settings.upload_root
            settings.upload_root = tmp
            db = self.open_temp_db()
            try:
                project = models.Project(name="路线项目")
                db.add(project)
                db.commit()
                db.refresh(project)

                empty = get_project_okf_bundle(project.id, db)
                self.assertFalse(empty["generated"])
                self.assertEqual(empty["files"], [])

                first = generate_okf_bundle(project.id, db)
                second = generate_okf_bundle(project.id, db)
                okf_files = db.query(models.KnowledgeFile).filter(models.KnowledgeFile.filepath.like(f"project-okf/{project.id}/%")).all()

                self.assertTrue(first["generated"])
                self.assertTrue(second["generated"])
                self.assertEqual(len(okf_files), len(OKF_BUNDLE_FILES))
            finally:
                db.close()
                settings.upload_root = original_upload_root


if __name__ == "__main__":
    unittest.main()
