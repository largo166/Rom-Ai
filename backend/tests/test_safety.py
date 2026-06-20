import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.routes.projects import get_project_mindmap
from app.safety import safe_json_loads, validate_directory, validate_path


class SafetyHelpersTest(unittest.TestCase):
    def test_safe_json_loads_returns_default_for_dirty_json(self):
        self.assertEqual(safe_json_loads("{bad", {}), {})
        self.assertEqual(safe_json_loads('{"ok": true}', {}), {"ok": True})
        self.assertEqual(safe_json_loads(["wrong"], {}), {})

    def test_validate_directory_rejects_empty_and_allows_real_folder(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                validate_directory(root)
            (root / "资料.md").write_text("ok", encoding="utf-8")
            self.assertEqual(validate_directory(root), root.resolve())

    @unittest.skipIf(not hasattr(os, "symlink"), "symlink not available")
    def test_validate_path_rejects_symlink_component(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            try:
                os.symlink(real, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted")
            with self.assertRaises(ValueError):
                validate_path(link, must_exist=True, must_be_dir=True)


class DirtyJsonRouteTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_project_mindmap_falls_back_when_json_is_dirty(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="脏数据项目")
            report = models.ProjectReport(report_type="startup_analysis", content_json="{bad")
            project.reports = [report]
            db.add(project)
            db.commit()
            db.refresh(project)

            result = get_project_mindmap(project.id, db)

            self.assertEqual(result, {"title": "项目启动分析", "nodes": []})
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
