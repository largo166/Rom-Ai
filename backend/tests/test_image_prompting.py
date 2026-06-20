import asyncio
import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.database import Base
from app.services.execution import run_agent_chat
from app.services.image_prompting import build_multiview_image_prompts


class ImagePromptingTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_builds_four_multiview_prompts_with_project_keywords(self):
        project = models.Project(
            name="石家庄市庄项目",
            city="石家庄",
            project_type="展示区",
            phase="方案",
            description="甲方希望强化宋式、抬板、坞壁和入口仪式感。",
        )
        result = build_multiview_image_prompts(project, user_prompt="生成宋式抬板多视角意向图")

        self.assertEqual(len(result["prompt_variants"]), 4)
        self.assertIn("宋式", result["keywords"])
        self.assertIn("抬板", result["keywords"])
        self.assertEqual(result["views"], ["总体鸟瞰", "入口人视", "庭院空间", "立面细节"])

    def test_ai_image_skill_keeps_four_prompts_when_key_is_missing(self):
        db = self.open_temp_db()
        old_key = settings.image_api_key
        settings.image_api_key = ""
        try:
            project = models.Project(
                name="石家庄市庄项目",
                city="石家庄",
                project_type="展示区",
                description="宋式、抬板、坞壁、院落。",
            )
            db.add(project)
            db.commit()
            db.refresh(project)

            result = asyncio.run(run_agent_chat(db, project, "为市庄项目生成宋式抬板AI生图", "ai_image_generation"))
            card = result["card"]
            output = json.loads(card.output_json)

            self.assertEqual(card.status, "not_configured")
            self.assertEqual(len(output["prompt_variants"]), 4)
            self.assertEqual(output["image_paths"], [])
            self.assertIn("未配置", output["message"])
        finally:
            settings.image_api_key = old_key
            db.close()


if __name__ == "__main__":
    unittest.main()
