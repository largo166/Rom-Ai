import unittest
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.database import Base
from app.services import delete_project_library, search_knowledge, summarize_meeting
from app.routes.projects import assign_project_task, create_communication, create_project_meeting, create_project_task, delete_project_execution_run, delete_project_file, delete_project_meeting, delete_project_task, parse_one_project_file, preview_project_file, sync_tencent_project_meeting_minutes, update_project_task
from app.routes.team import (
    add_team_member,
    get_all_members,
    get_network_member_workload,
    update_global_team_member,
)
import app.routes.projects as project_routes


class ProjectDeleteTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_delete_project_library_removes_project_records_and_managed_files(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                project = models.Project(name="待删除项目", city="杭州")
                db.add(project)
                db.commit()
                db.refresh(project)

                project_dir = Path(tmp) / "projects" / project.id
                project_dir.mkdir(parents=True)
                project_file = project_dir / "资料.md"
                project_file.write_text("项目资料", encoding="utf-8")
                source_file = Path(tmp) / "source.md"
                source_file.write_text("原始文件", encoding="utf-8")

                db.add(models.ProjectFile(project_id=project.id, filename="资料.md", filepath=str(project_file), filetype="md", filesize=project_file.stat().st_size))
                db.add(models.ProjectTask(project_id=project.id, task_name="任务"))
                db.add(models.InboxItem(original_filename="资料.md", source_path=str(source_file), temp_path=str(source_file), project_id=project.id, status="已归档"))
                db.commit()

                result = delete_project_library(db, project.id, upload_root=Path(tmp))

                self.assertTrue(result["deleted"])
                self.assertEqual(result["deleted_project_id"], project.id)
                self.assertIsNone(db.get(models.Project, project.id))
                self.assertEqual(db.query(models.ProjectFile).filter_by(project_id=project.id).count(), 0)
                self.assertEqual(db.query(models.ProjectTask).filter_by(project_id=project.id).count(), 0)
                self.assertFalse(project_dir.exists())
                self.assertTrue(source_file.exists())
                inbox_item = db.query(models.InboxItem).first()
                self.assertEqual(inbox_item.project_id, "")
                self.assertEqual(inbox_item.status, "待确认")
            finally:
                db.close()


class ProjectTeamWorkflowTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_global_human_member_can_be_renamed_and_listed_with_ai_members(self):
        db = self.open_temp_db()
        try:
            member = models.TeamMember(name="张工", role="方案主创", skills='["总图"]')
            ai = models.DigitalEmployee(name="AI资料管理员", role="资料整理", skills='["资料"]', avatar="📎")
            db.add_all([member, ai])
            db.commit()
            db.refresh(member)

            updated = update_global_team_member(member.id, schemas.TeamMemberUpdate(name="张三", role="项目经理"), db)
            members = get_all_members(db)

            self.assertEqual(updated.name, "张三")
            self.assertTrue(any(item["id"] == member.id and item["type"] == "human" and item["name"] == "张三" for item in members["members"]))
            self.assertTrue(any(item["id"] == ai.id and item["type"] == "digital_employee" for item in members["members"]))
        finally:
            db.close()

    def test_tencent_minutes_unavailable_returns_business_status(self):
        db = self.open_temp_db()
        original_sync = project_routes.sync_tencent_meeting_minutes
        try:
            project = models.Project(name="会议项目", city="杭州")
            meeting = models.Meeting(title="启动会", recording_url="https://meeting.tencent.com/dm/example")
            project.meetings = [meeting]
            db.add(project)
            db.commit()
            db.refresh(project)
            db.refresh(meeting)

            def unavailable(_db, _meeting):
                raise project_routes.TencentMinutesUnavailableError("暂未查询到腾讯会议录制文件")

            project_routes.sync_tencent_meeting_minutes = unavailable

            with self.assertRaises(Exception) as context:
                sync_tencent_project_meeting_minutes(project.id, meeting.id, db)

            self.assertEqual(context.exception.status_code, 409)
            self.assertEqual(context.exception.detail, "暂未查询到腾讯会议录制文件")
        finally:
            project_routes.sync_tencent_meeting_minutes = original_sync
            db.close()

    def test_meeting_summary_requires_real_transcript(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="会议项目", city="杭州")
            meeting = models.Meeting(title="启动会", agenda="模板议程", transcript="")
            project.meetings = [meeting]
            db.add(project)
            db.commit()
            db.refresh(meeting)

            with self.assertRaises(ValueError) as context:
                asyncio.run(summarize_meeting(db, meeting))

            self.assertEqual(str(context.exception), "请先同步腾讯会议真实转写，再生成AI纪要")
        finally:
            db.close()

    def test_meeting_summary_is_saved_as_project_knowledge(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="会议项目", city="杭州")
            meeting = models.Meeting(
                title="启动会",
                transcript="韩暄：真实会议确认先复核消防登高面和日照退界。",
            )
            project.meetings = [meeting]
            db.add(project)
            db.commit()
            db.refresh(meeting)

            asyncio.run(summarize_meeting(db, meeting))
            chunks = search_knowledge(db, "真实会议 消防登高面 日照退界", limit=5)
            summary_file = db.query(models.KnowledgeFile).filter_by(
                filepath=f"project-context/{project.id}/meetings/{meeting.id}.md"
            ).one()

            self.assertTrue(chunks)
            self.assertTrue(any("消防登高面" in chunk.content for chunk in chunks))
            self.assertTrue(any(f"project-context/{project.id}/meeting-transcripts/{meeting.id}.md" in chunk.path for chunk in chunks))
            summary_content = "\n".join(
                chunk.content for chunk in db.query(models.KnowledgeChunk).filter_by(file_id=summary_file.id)
            )
            self.assertNotIn("韩暄：真实会议确认", summary_content)
        finally:
            db.close()

    def test_create_project_meeting_does_not_invent_agenda(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="会议项目", city="杭州")
            db.add(project)
            db.commit()
            db.refresh(project)

            meeting = create_project_meeting(project.id, schemas.ProjectMeetingCreate(title="启动会"), db)

            self.assertEqual(meeting.agenda, "")
        finally:
            db.close()

    def test_delete_project_meeting_removes_its_knowledge_deposit(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="会议项目", city="杭州")
            meeting = models.Meeting(title="启动会", transcript="确认消防复核。")
            project.meetings = [meeting]
            db.add(project)
            db.commit()
            db.refresh(meeting)

            asyncio.run(summarize_meeting(db, meeting))
            indexed_path = f"project-context/{project.id}/meetings/{meeting.id}.md"
            knowledge_file = db.query(models.KnowledgeFile).filter_by(filepath=indexed_path).one()
            knowledge_file_id = knowledge_file.id
            transcript_file = db.query(models.KnowledgeFile).filter_by(
                filepath=f"project-context/{project.id}/meeting-transcripts/{meeting.id}.md"
            ).one()
            transcript_file_id = transcript_file.id

            result = delete_project_meeting(project.id, meeting.id, db)

            self.assertTrue(result["deleted"])
            self.assertIsNone(db.get(models.Meeting, meeting.id))
            self.assertIsNone(db.get(models.KnowledgeFile, knowledge_file_id))
            self.assertIsNone(db.get(models.KnowledgeFile, transcript_file_id))
            self.assertEqual(db.query(models.KnowledgeChunk).filter_by(file_id=knowledge_file_id).count(), 0)
        finally:
            db.close()

    def test_delete_project_meeting_rejects_meeting_from_another_project(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="会议项目")
            other_project = models.Project(name="其他项目")
            meeting = models.Meeting(title="其他项目会议")
            other_project.meetings = [meeting]
            db.add_all([project, other_project])
            db.commit()
            db.refresh(meeting)

            with self.assertRaises(Exception) as context:
                delete_project_meeting(project.id, meeting.id, db)

            self.assertEqual(context.exception.status_code, 404)
            self.assertIsNotNone(db.get(models.Meeting, meeting.id))
        finally:
            db.close()

    def test_project_team_accepts_network_member_and_assigns_project_task(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="杭州萧山湘北强排", city="杭州")
            member = models.TeamMember(name="李工", role="总图负责人", skills='["总图"]')
            db.add_all([project, member])
            db.commit()
            db.refresh(project)
            db.refresh(member)
            task = models.ProjectTask(project_id=project.id, task_name="复核总图指标", owner_role="总图负责人")
            db.add(task)
            db.commit()
            db.refresh(task)

            assignment = add_team_member(
                project.id,
                schemas.TeamAssignmentCreate(
                    member_id=member.id,
                    member_type="human",
                    member_name=member.name,
                    role="总图负责人",
                    responsibilities="复核总图指标",
                ),
                db,
            )
            assigned_task = assign_project_task(
                project.id,
                task.id,
                schemas.ProjectTaskAssigneeUpdate(
                    assignee_type="human",
                    assignee_id=member.id,
                    assignee_name=member.name,
                ),
                db,
            )
            workload = get_network_member_workload("human", member.id, db)

            self.assertEqual(assignment.member_id, member.id)
            self.assertEqual(assigned_task.assignee_id, member.id)
            self.assertEqual(assigned_task.assignee_name, "李工")
            self.assertEqual(assigned_task.owner_role, "李工")
            self.assertEqual(workload["task_count"], 1)
            self.assertEqual(workload["project_count"], 1)
            self.assertEqual(workload["tasks"][0]["task_name"], "复核总图指标")
        finally:
            db.close()

    def test_project_task_create_and_status_update_use_startup_task_table(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="任务项目", city="杭州")
            db.add(project)
            db.commit()
            db.refresh(project)

            task = create_project_task(
                project.id,
                schemas.ProjectTaskCreate(task_name="整理启动资料", priority="high", owner_role="项目经理"),
                db,
            )
            updated = update_project_task(project.id, task.id, schemas.ProjectTaskUpdate(status="doing"), db)

            self.assertEqual(task.project_id, project.id)
            self.assertEqual(task.task_name, "整理启动资料")
            self.assertEqual(updated.status, "doing")
            self.assertEqual(db.query(models.ProjectTask).filter_by(project_id=project.id).count(), 1)
        finally:
            db.close()

    def test_project_task_can_be_fully_edited_and_deleted(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="任务项目")
            db.add(project)
            db.commit()
            task = create_project_task(project.id, schemas.ProjectTaskCreate(task_name="初始任务"), db)

            updated = update_project_task(
                project.id,
                task.id,
                schemas.ProjectTaskUpdate(task_name="复核方案", risk_level="high", output_requirement="复核清单"),
                db,
            )
            result = delete_project_task(project.id, task.id, db)

            self.assertEqual(updated.task_name, "复核方案")
            self.assertEqual(updated.risk_level, "high")
            self.assertEqual(updated.output_requirement, "复核清单")
            self.assertTrue(result["deleted"])
            self.assertIsNone(db.get(models.ProjectTask, task.id))
        finally:
            db.close()

    def test_project_file_can_be_previewed_reparsed_and_safely_deleted(self):
        with TemporaryDirectory() as tmp:
            db = self.open_temp_db()
            try:
                path = Path(tmp) / "资料.txt"
                path.write_text("真实项目资料", encoding="utf-8")
                project = models.Project(name="资料项目")
                project_file = models.ProjectFile(filename=path.name, filepath=str(path), parsed_text="旧内容")
                project.files = [project_file]
                db.add(project)
                db.commit()
                db.refresh(project_file)

                preview = preview_project_file(project.id, project_file.id, db)
                parsed = parse_one_project_file(project.id, project_file.id, db)
                result = delete_project_file(project.id, project_file.id, db)

                self.assertEqual(preview["content"], "旧内容")
                self.assertIn("真实项目资料", parsed.parsed_text)
                self.assertTrue(result["deleted"])
                self.assertTrue(path.exists())
            finally:
                db.close()

    def test_execution_history_delete_only_removes_project_execution_run(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="执行台项目")
            execution_run = models.AgentRun(agent_id="project-execution")
            other_run = models.AgentRun(agent_id="project-parser")
            project.agent_runs = [execution_run, other_run]
            db.add(project)
            db.commit()
            db.refresh(execution_run)
            db.refresh(other_run)

            result = delete_project_execution_run(project.id, execution_run.id, db)

            self.assertTrue(result["deleted"])
            self.assertIsNone(db.get(models.AgentRun, execution_run.id))
            self.assertIsNotNone(db.get(models.AgentRun, other_run.id))
            with self.assertRaises(Exception) as context:
                delete_project_execution_run(project.id, other_run.id, db)
            self.assertEqual(context.exception.status_code, 404)
        finally:
            db.close()


class CommunicationEndpointTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_create_communication_persists_meeting_and_generates_minutes(self):
        db = self.open_temp_db()
        try:
            project = models.Project(name="沟通测试项目", city="杭州", phase="方案")
            db.add(project)
            db.commit()
            db.refresh(project)

            payload = schemas.CommunicationCreate(
                communication_type="phone",
                title="电话沟通",
                participants="甲方王总",
                content="甲方说：这个方案不够高级，希望入口再大气一点。",
                occurred_at="2026-06-20T10:00:00+08:00",
            )
            result = asyncio.run(create_communication(project.id, payload, db))

            meeting = result["meeting"]
            self.assertEqual(meeting.project_id, project.id)
            self.assertEqual(meeting.meeting_type, "phone")
            self.assertIn("不够高级", meeting.transcript)
            self.assertEqual(meeting.status, "summarized")
            self.assertTrue(result["minutes"]["meeting_content"] or result["minutes"]["action_items"] is not None)
            self.assertTrue(len(result["rule_translations"]) > 0)
            self.assertTrue(db.query(models.ProjectChangeEvent).filter_by(event_type="communication_added").count() >= 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
