import unittest
from datetime import datetime
from tempfile import TemporaryDirectory
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
import app.services as services
from app.services import (
    build_startup_analysis_prompt,
    build_project_execution_prompt,
    classify_project_execution_instruction,
    build_tencent_records_query,
    deposit_startup_analysis_to_knowledge,
    extract_tencent_meeting_metadata,
    parse_tencent_meeting_result,
    parse_tencent_record_address_result,
    parse_tencent_record_result,
    extract_tencent_smart_minutes_text,
    sync_tencent_meeting_minutes,
    pending_analysis_files,
    parse_deepseek_models,
    scan_vault_directory,
    list_knowledge_files,
    search_knowledge,
)
from app.database import Base


class StartupAnalysisPromptTest(unittest.TestCase):
    def test_prompt_includes_uploaded_file_parsed_text(self):
        project = models.Project(
            name="湖畔住宅",
            city="杭州",
            project_type="住宅",
            phase="概念方案",
            description="低密改善型住宅",
        )
        project.files = [
            models.ProjectFile(
                filename="设计任务书.md",
                filetype="md",
                parse_status="parsed",
                parsed_text="业主要求重点分析洋房日照、消防登高面和地下车库流线。",
            )
        ]

        prompt = build_startup_analysis_prompt(project, [])

        self.assertIn("设计任务书.md", prompt)
        self.assertIn("洋房日照、消防登高面和地下车库流线", prompt)

    def test_prompt_can_limit_context_to_pending_analysis_files(self):
        project = models.Project(name="湖畔住宅")
        old_file = models.ProjectFile(
            filename="旧任务书.md",
            filetype="md",
            parse_status="parsed",
            parsed_text="旧文件内容不应重复进入本次模型分析。",
            analysis_status="analyzed",
        )
        new_file = models.ProjectFile(
            filename="新增红线图说明.md",
            filetype="md",
            parse_status="parsed",
            parsed_text="新增文件要求复核道路退界和消防登高面。",
            analysis_status="pending",
        )
        project.files = [old_file, new_file]

        prompt = build_startup_analysis_prompt(project, [], files=pending_analysis_files(project))

        self.assertIn("新增红线图说明.md", prompt)
        self.assertIn("道路退界和消防登高面", prompt)
        self.assertNotIn("旧任务书.md", prompt)
        self.assertNotIn("旧文件内容不应重复进入本次模型分析", prompt)


class ProjectExecutionPromptTest(unittest.TestCase):
    def test_execution_instruction_classifier_allows_greetings(self):
        project = models.Project(name="湘北强排", city="杭州", project_type="住宅")

        result = classify_project_execution_instruction(project, "你好")

        self.assertEqual(result, "greeting")

    def test_execution_instruction_classifier_rejects_unrelated_requests(self):
        project = models.Project(name="湘北强排", city="杭州", project_type="住宅")

        result = classify_project_execution_instruction(project, "帮我写一首关于咖啡的诗")

        self.assertEqual(result, "unrelated")

    def test_execution_prompt_includes_project_context_and_knowledge(self):
        project = models.Project(
            name="湘北强排",
            city="杭州",
            project_type="住宅",
            phase="强排",
            description="低密住宅强排",
        )
        project.tasks = [
            models.ProjectTask(task_name="日照复核", owner_role="总图负责人", priority="高", output_requirement="输出日照风险说明")
        ]
        project.meetings = [
            models.Meeting(title="启动会", summary="会议确认先复核退界和消防登高面。")
        ]
        chunks = [
            models.KnowledgeChunk(
                heading="历史强排经验",
                content="类似项目需先确认日照口径、楼间距和规划限高。",
                path="project-deposits/old/startup-analysis.md",
            )
        ]

        prompt = build_project_execution_prompt(project, "帮我拆总图任务", chunks)

        self.assertIn("湘北强排", prompt)
        self.assertIn("帮我拆总图任务", prompt)
        self.assertIn("日照复核", prompt)
        self.assertIn("历史强排经验", prompt)
        self.assertIn("直接回应用户发来的具体问题", prompt)
        self.assertIn("与当前项目无关", prompt)


class DeepSeekModelsTest(unittest.TestCase):
    def test_parse_models_returns_ids_and_owner(self):
        payload = {
            "object": "list",
            "data": [
                {"id": "deepseek-v4-flash", "object": "model", "owned_by": "deepseek"},
                {"id": "deepseek-v4-pro", "object": "model", "owned_by": "deepseek"},
            ],
        }

        models = parse_deepseek_models(payload)

        self.assertEqual(
            models,
            [
                {"id": "deepseek-v4-flash", "owned_by": "deepseek"},
                {"id": "deepseek-v4-pro", "owned_by": "deepseek"},
            ],
        )


class KnowledgeIndexResultTest(unittest.TestCase):
    def open_temp_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    def test_scan_vault_returns_skipped_files_for_frontend_message(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.md").write_text("# 项目知识\n正文", encoding="utf-8")
            (root / "skip.zip").write_text("skip", encoding="utf-8")
            db = self.open_temp_db()
            try:
                result = scan_vault_directory(db, root, clear_existing=True)
            finally:
                db.close()

        self.assertIn("skipped_files", result)
        self.assertIsInstance(result["skipped_files"], list)

    def test_scan_vault_returns_dashboard_stats_shape(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.md").write_text("# 项目知识\n正文", encoding="utf-8")
            db = self.open_temp_db()
            try:
                result = scan_vault_directory(db, root, clear_existing=True)
            finally:
                db.close()

        self.assertEqual(result["stats"]["total_files"], 1)
        self.assertEqual(result["stats"]["markdown_files"], 1)
        self.assertEqual(result["stats"]["pdf_docx_xlsx_files"], 0)

    def test_startup_analysis_deposit_is_searchable_knowledge(self):
        db = self.open_temp_db()
        try:
            project = models.Project(
                name="湘北强排",
                city="杭州",
                project_type="住宅",
                phase="强排",
            )
            db.add(project)
            db.commit()
            payload = {
                "project_summary": {"summary": "需要复核日照、退界和消防登高面。"},
                "technical_focus_cards": [
                    {
                        "title": "日照退界复核",
                        "dimension": "日照/退界",
                        "summary": "结合知识库经验，先锁定楼栋高度、间距和相邻地块遮挡。",
                        "checkpoints": ["复核楼间距", "确认相邻地块条件"],
                        "source_refs": ["历史强排项目"],
                    }
                ],
                "task_breakdown": [
                    {
                        "task_name": "强排指标复核",
                        "owner_role": "总图负责人",
                        "priority": "高",
                        "output_requirement": "形成指标复核表。",
                    }
                ],
                "risk_list": ["日照口径不明确会影响排布判断。"],
                "open_questions": ["是否已有正式日照条件？"],
                "source_refs": [{"source_path": "历史项目/强排复盘.md", "quote": "日照先行"}],
            }

            deposit_startup_analysis_to_knowledge(db, project, payload, "report-1")
            chunks = search_knowledge(db, "湘北强排 日照 退界", limit=5)

            self.assertTrue(chunks)
            self.assertTrue(any("日照退界复核" in chunk.content for chunk in chunks))
            self.assertTrue(any("project-deposits" in chunk.path for chunk in chunks))
        finally:
            db.close()

    def test_list_knowledge_files_supports_search_and_limit(self):
        db = self.open_temp_db()
        try:
            db.add(models.KnowledgeFile(filename="振三街定位报告.pdf", filepath="/Users/leslie/知识库/振三街定位报告.pdf", filetype="pdf", filesize=1024))
            db.add(models.KnowledgeFile(filename="台州任务书.docx", filepath="/Users/leslie/知识库/台州任务书.docx", filetype="docx", filesize=2048))
            db.commit()

            result = list_knowledge_files(db, q="振三街", limit=10)

            self.assertEqual(result["total"], 1)
            self.assertEqual(result["items"][0]["filename"], "振三街定位报告.pdf")
            self.assertEqual(result["items"][0]["filepath"], "/Users/leslie/知识库/振三街定位报告.pdf")
        finally:
            db.close()


class TencentMeetingResultTest(unittest.TestCase):
    def test_parse_meeting_code_and_join_url_from_tool_text(self):
        text = "创建成功\\n会议号：123 456 789\\n入会链接：https://meeting.tencent.com/dm/abc123\\nX-Tc-Trace: trace-001"

        parsed = parse_tencent_meeting_result(text)

        self.assertEqual(parsed["meeting_code"], "123456789")
        self.assertEqual(parsed["join_url"], "https://meeting.tencent.com/dm/abc123")
        self.assertEqual(parsed["trace"], "trace-001")

    def test_extract_metadata_from_saved_meeting_link(self):
        meeting = models.Meeting(
            recording_url=(
                "https://meeting.tencent.com/dm/abc123\n"
                "会议号：123456789\n"
                "meeting_id：987654321\n"
                "X-Tc-Trace：trace-001"
            )
        )

        metadata = extract_tencent_meeting_metadata(meeting)

        self.assertEqual(metadata["meeting_code"], "123456789")
        self.assertEqual(metadata["meeting_id"], "987654321")

    def test_parse_record_file_id_and_smart_minutes(self):
        text = "查询成功\\nrecord_file_id: 456789\\nmeeting_record_id: 987654\\n智能纪要：本次会议确认总图退界复核。"

        parsed = parse_tencent_record_result(text)

        self.assertEqual(parsed["record_file_id"], "456789")
        self.assertEqual(parsed["meeting_record_id"], "987654")
        self.assertIn("总图退界复核", parsed["raw"])

    def test_parse_record_file_ids_from_tencent_json_list(self):
        text = (
            '{"status_code":200,"body":"{'
            '\\"record_meetings\\":[{'
            '\\"media_start_time\\":\\"2026-06-11T13:52:03+08:00\\",'
            '\\"meeting_record_id\\":\\"2064948756988846080\\",'
            '\\"record_files\\":[{\\"record_file_id\\":\\"2064948756988846081\\"}]'
            '},{'
            '\\"media_start_time\\":\\"2026-06-11T13:47:23+08:00\\",'
            '\\"meeting_record_id\\":\\"2064947583555862528\\",'
            '\\"record_files\\":[{\\"record_file_id\\":\\"2064947583555862529\\"}]'
            '}]}"}'
        )

        parsed = parse_tencent_record_result(text)

        self.assertEqual(parsed["record_file_id"], "2064948756988846081")
        self.assertEqual(parsed["meeting_record_id"], "2064948756988846080")
        self.assertEqual(
            parsed["records"],
            [
                {"record_file_id": "2064948756988846081", "meeting_record_id": "2064948756988846080"},
                {"record_file_id": "2064947583555862529", "meeting_record_id": "2064947583555862528"},
            ],
        )

    def test_parse_record_view_address_and_trace(self):
        text = (
            '{"status_code":200,"headers":{"X-Tc-Trace":"trace-001","rpcUuid":"rpc-001"},'
            '"body":"{\\"record_files\\":[{\\"view_address\\":\\"https://meeting.tencent.com/crw/example\\"}]}"}'
        )

        parsed = parse_tencent_record_address_result(text)

        self.assertEqual(parsed["view_address"], "https://meeting.tencent.com/crw/example")
        self.assertEqual(parsed["trace"], "trace-001")
        self.assertEqual(parsed["rpc_uuid"], "rpc-001")

    def test_extract_smart_minutes_text_from_tencent_json(self):
        text = (
            '{"status_code":200,"body":"{'
            '\\"meeting_minute\\":{\\"minute\\":\\"会议主题：本地AI设计工作台产品演示\\\\n会议摘要：已生成。\\"}'
            '}"}'
        )

        minutes = extract_tencent_smart_minutes_text(text)

        self.assertIn("会议主题：本地AI设计工作台产品演示", minutes)
        self.assertNotIn("status_code", minutes)

    def test_build_records_query_falls_back_to_meeting_time(self):
        meeting = models.Meeting(
            recording_url="https://meeting.tencent.com/dm/abc123",
            date=datetime(2026, 6, 9, 19, 29),
        )

        query = build_tencent_records_query(meeting)

        self.assertEqual(query["page_size"], 10)
        self.assertIn("start_time", query)
        self.assertIn("end_time", query)

    def test_sync_tencent_minutes_stores_only_real_transcript(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
        original_call = services.call_tencent_meeting_tool
        try:
            project = models.Project(name="会议项目")
            meeting = models.Meeting(title="真实会议", date=datetime(2026, 6, 11, 13, 46), summary="旧纪要")
            project.meetings = [meeting]
            db.add(project)
            db.commit()
            db.refresh(meeting)

            def fake_call(name, arguments, timeout=60):
                if name == "get_records_list":
                    return (
                        '{"status_code":200,"body":"{'
                        '\\"record_meetings\\":[{\\"meeting_record_id\\":\\"mr1\\",'
                        '\\"record_files\\":[{\\"record_file_id\\":\\"rf1\\"}]}]'
                        '}"}'
                    )
                if name == "get_transcripts_details":
                    return (
                        '{"status_code":200,"body":"{'
                        '\\"minutes\\":{\\"paragraphs\\":[{\\"speaker\\":{\\"user_name\\":\\"韩暄\\"},'
                        '\\"sentences\\":[{\\"words\\":[{\\"text\\":\\"真实转写内容\\"}]}]}]}}'
                        '"}'
                    )
                if name == "get_record_addresses":
                    return (
                        '{"status_code":200,"headers":{"X-Tc-Trace":"trace-001","rpcUuid":"rpc-001"},'
                        '"body":"{\\"record_files\\":[{\\"view_address\\":\\"https://meeting.tencent.com/crw/example\\"}]}"}'
                    )
                raise AssertionError(f"unexpected tool call: {name}")

            services.call_tencent_meeting_tool = fake_call

            synced = sync_tencent_meeting_minutes(db, meeting)

            self.assertIn("韩暄：真实转写内容", synced.transcript)
            self.assertEqual(synced.summary, "旧纪要")
            self.assertEqual(synced.status, "transcribed")
            self.assertIn("录屏查看：https://meeting.tencent.com/crw/example", synced.recording_url)
            self.assertIn("录屏 X-Tc-Trace：trace-001", synced.recording_url)
        finally:
            services.call_tencent_meeting_tool = original_call
            db.close()


if __name__ == "__main__":
    unittest.main()
