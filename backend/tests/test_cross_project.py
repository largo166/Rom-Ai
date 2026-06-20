import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services.analysis import build_startup_analysis_payload
from app.services.cross_project import collect_cross_project_experience
from app.services.knowledge import upsert_knowledge_markdown


class CrossProjectExperienceTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_collects_source_backed_experience_for_same_city_project(self):
        db = self.open_temp_db()
        try:
            current = models.Project(name="石家庄市庄项目", city="石家庄", project_type="住宅", phase="方案")
            history = models.Project(name="石家庄长安天曜项目", city="石家庄", project_type="住宅", phase="方案")
            db.add_all([current, history])
            db.commit()
            db.refresh(current)
            db.refresh(history)

            upsert_knowledge_markdown(
                db,
                f"project-context/{history.id}/technical-risk.md",
                "石家庄长安天曜技术风险",
                "# 技术风险\n\n石家庄住宅项目需要重点复核日照间距、道路退距、限高和甲方汇报周期。",
                ["石家庄", "住宅", "日照", "退距"],
            )
            db.commit()

            refs = collect_cross_project_experience(db, current, limit=3)
            payload = build_startup_analysis_payload(current, [], cross_project_refs=refs)

            self.assertTrue(refs)
            self.assertIn("石家庄", refs[0]["hit_reason"])
            self.assertIn("technical-risk.md", refs[0]["source_path"])
            self.assertEqual(payload["cross_project_refs"], refs)
            self.assertTrue(any("日照" in ref["quote"] for ref in payload["source_refs"]))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
