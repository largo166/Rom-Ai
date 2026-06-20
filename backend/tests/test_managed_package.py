import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.database import Base
from app.services.knowledge import search_knowledge
from app.services.managed_package import build_managed_package


class ManagedPackageTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_build_managed_package_keeps_source_and_indexes_project_materials(self):
        with TemporaryDirectory() as tmp:
            original_upload_root = settings.upload_root
            settings.upload_root = str(Path(tmp) / "uploads")
            db = self.open_temp_db()
            try:
                source_dir = Path(tmp) / "石家庄市庄项目"
                source_dir.mkdir()
                source_file = source_dir / "任务书.md"
                source_file.write_text("市庄项目需要关注日照、退距、宋式立面与抬板空间。", encoding="utf-8")
                unsupported = source_dir / "临时文件.tmp"
                unsupported.write_text("不应入库", encoding="utf-8")

                project = models.Project(name="石家庄市庄项目", city="石家庄", project_type="住宅", phase="方案")
                db.add(project)
                db.commit()
                db.refresh(project)

                result = build_managed_package(db, source_dir=source_dir, project=project)

                self.assertEqual(result["indexed_files"], 1)
                self.assertTrue(source_file.exists())
                self.assertTrue(unsupported.exists())
                self.assertTrue(Path(result["manifest_path"]).exists())
                self.assertTrue((Path(result["package_root"]) / "original_refs.json").exists())
                self.assertEqual(db.query(models.ProjectFile).filter_by(project_id=project.id).count(), 1)

                chunks = search_knowledge(db, "市庄 日照 退距 宋式 抬板", limit=8)
                self.assertTrue(chunks)
                self.assertTrue(any("managed-package" in chunk.path for chunk in chunks))
                self.assertTrue(any("原始路径" in chunk.content or "日照" in chunk.content for chunk in chunks))
            finally:
                db.close()
                settings.upload_root = original_upload_root


if __name__ == "__main__":
    unittest.main()
