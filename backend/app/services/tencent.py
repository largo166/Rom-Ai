"""tencent.py — 腾讯会议 API 调用与会议纪要同步"""
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.json_safety import safe_json_dump, safe_json_parse

TENCENT_MEETING_SCRIPT = Path.home() / ".codex" / "skills" / "tencent-meeting-mcp" / "scripts" / "tencent_meeting.py"


class TencentMinutesUnavailableError(RuntimeError):
    pass


def parse_tencent_meeting_result(text: str) -> dict[str, str]:
    text = text.replace("\\n", "\n")
    code_match = re.search(r"(?:会议号|meeting_code|meeting code)\s*[：:]\s*([0-9\s-]{9,})", text, re.I)
    url_match = re.search(r"https://meeting\.tencent\.com/[^\\\s，。)）]+", text)
    trace_match = re.search(r"(?:X-Tc-Trace|rpcUuid)\s*[：:]\s*([^\s，。]+)", text, re.I)
    meeting_id_match = re.search(r"(?:meeting_id|会议ID|会议id)\s*[：:]\s*([0-9]+)", text, re.I)
    return {
        "meeting_code": re.sub(r"\D", "", code_match.group(1)) if code_match else "",
        "join_url": url_match.group(0) if url_match else "",
        "trace": trace_match.group(1) if trace_match else "",
        "meeting_id": meeting_id_match.group(1) if meeting_id_match else "",
        "raw": text,
    }


def _load_tencent_json_payload(text: str) -> Any:
    outer = safe_json_parse(text, default=None, field_name="tencent_outer")
    if outer is None:
        return None
    body = outer.get("body") if isinstance(outer, dict) else None
    if isinstance(body, str):
        inner = safe_json_parse(body, default=None, field_name="tencent_body")
        return inner if inner is not None else outer
    return outer


def _tencent_response_error(text: str) -> str:
    payload = safe_json_parse(text, default=None, field_name="tencent_error_outer")
    if not isinstance(payload, dict):
        return ""
    status_code = int(payload.get("status_code") or 200)
    if status_code < 400:
        return ""
    body = payload.get("body")
    body_payload: Any = {}
    if isinstance(body, str):
        body_payload = safe_json_parse(body, default={}, field_name="tencent_error_body")
    message = ""
    if isinstance(body_payload, dict):
        error_info = body_payload.get("error_info")
        if isinstance(error_info, dict):
            message = str(error_info.get("message") or "")
    trace = ""
    headers = payload.get("headers")
    if isinstance(headers, dict):
        trace = str(headers.get("X-Tc-Trace") or headers.get("rpcUuid") or "")
    return "；".join(part for part in [message or f"腾讯会议接口返回 {status_code}", f"trace={trace}" if trace else ""] if part)


def extract_tencent_transcript_text(text: str) -> str:
    payload = _load_tencent_json_payload(text)
    body = payload.get("body") if isinstance(payload, dict) else None
    if isinstance(body, str):
        body_payload = safe_json_parse(body, default=None, field_name="tencent_transcript_body")
        if body_payload is None:
            return text
    else:
        body_payload = payload
    if not isinstance(body_payload, dict):
        return text
    minutes = body_payload.get("minutes")
    if not isinstance(minutes, dict):
        return text
    lines: list[str] = []
    for paragraph in minutes.get("paragraphs", []) or []:
        if not isinstance(paragraph, dict):
            continue
        speaker = paragraph.get("speaker")
        speaker_name = ""
        if isinstance(speaker, dict):
            speaker_name = str(speaker.get("user_name") or "").strip()
        words: list[str] = []
        for sentence in paragraph.get("sentences", []) or []:
            if not isinstance(sentence, dict):
                continue
            for word in sentence.get("words", []) or []:
                if isinstance(word, dict):
                    words.append(str(word.get("text") or ""))
        content = "".join(words).strip()
        if content:
            lines.append(f"{speaker_name}：{content}" if speaker_name else content)
    return "\n".join(lines)


def extract_tencent_smart_minutes_text(text: str) -> str:
    payload = _load_tencent_json_payload(text)
    body = payload.get("body") if isinstance(payload, dict) else None
    if isinstance(body, str):
        body_payload = safe_json_parse(body, default=None, field_name="tencent_minutes_body")
        if body_payload is None:
            return text
    else:
        body_payload = payload
    if not isinstance(body_payload, dict):
        return text
    meeting_minute = body_payload.get("meeting_minute")
    if isinstance(meeting_minute, dict):
        minute = str(meeting_minute.get("minute") or "").strip()
        if minute:
            return minute
    return text


def parse_tencent_record_result(text: str) -> dict[str, Any]:
    text = text.replace("\\n", "\n")
    payload = _load_tencent_json_payload(text)
    records: list[dict[str, str]] = []
    if isinstance(payload, dict):
        for meeting_record in payload.get("record_meetings", []) or []:
            if not isinstance(meeting_record, dict):
                continue
            meeting_record_id = str(meeting_record.get("meeting_record_id") or "")
            for record_file in meeting_record.get("record_files", []) or []:
                if not isinstance(record_file, dict):
                    continue
                record_file_id = str(record_file.get("record_file_id") or "")
                if record_file_id:
                    records.append({"record_file_id": record_file_id, "meeting_record_id": meeting_record_id})

    record_file_match = re.search(r"(?:record_file_id|recordFileId|录制文件ID|录制文件id)\s*[：:]\s*([0-9]+)", text, re.I)
    meeting_record_match = re.search(r"(?:meeting_record_id|meetingRecordId|会议录制ID|会议录制id)\s*[：:]\s*([0-9]+)", text, re.I)
    download_match = re.search(r"https?://[^\\\s，。)）]+", text)
    first_record = records[0] if records else {}
    return {
        "record_file_id": first_record.get("record_file_id") or (record_file_match.group(1) if record_file_match else ""),
        "meeting_record_id": first_record.get("meeting_record_id") or (meeting_record_match.group(1) if meeting_record_match else ""),
        "download_url": download_match.group(0) if download_match else "",
        "records": records,
        "raw": text,
    }


def parse_tencent_record_address_result(text: str) -> dict[str, str]:
    payload = _load_tencent_json_payload(text)
    view_address = ""
    if isinstance(payload, dict):
        for record_file in payload.get("record_files", []) or []:
            if isinstance(record_file, dict) and record_file.get("view_address"):
                view_address = str(record_file["view_address"])
                break
    outer = safe_json_parse(text, default={}, field_name="tencent_record_address") if text.strip().startswith("{") else {}
    headers = outer.get("headers") if isinstance(outer, dict) else {}
    return {
        "view_address": view_address,
        "trace": str(headers.get("X-Tc-Trace") or "") if isinstance(headers, dict) else "",
        "rpc_uuid": str(headers.get("rpcUuid") or "") if isinstance(headers, dict) else "",
    }


def extract_tencent_meeting_metadata(meeting: models.Meeting) -> dict[str, str]:
    legacy = parse_tencent_meeting_result("\n".join([meeting.recording_url or "", meeting.agenda or ""]))
    return {
        **legacy,
        "meeting_code": meeting.tencent_meeting_code or legacy["meeting_code"],
        "meeting_id": meeting.tencent_meeting_id or legacy["meeting_id"],
        "join_url": meeting.tencent_join_url or legacy["join_url"],
    }


def extract_tencent_transcript_paragraph_ids(text: str) -> list[str]:
    payload = _load_tencent_json_payload(text)
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            pid = value.get("pid") or value.get("paragraph_id")
            if pid is not None and str(pid) not in found:
                found.append(str(pid))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return found


def fetch_complete_tencent_transcript(record_file_id: str) -> str:
    import app.services as _svc
    try:
        paragraph_text = _svc.call_tencent_meeting_tool("get_transcripts_paragraphs", {"record_file_id": record_file_id})
        paragraph_ids = extract_tencent_transcript_paragraph_ids(paragraph_text)
    except Exception:
        paragraph_ids = []
    if not paragraph_ids:
        paragraph_ids = ["0"]
    lines: list[str] = []
    seen: set[str] = set()
    for pid in paragraph_ids:
        detail = _svc.call_tencent_meeting_tool(
            "get_transcripts_details",
            {"record_file_id": record_file_id, "pid": pid, "limit": "50"},
        )
        for line in extract_tencent_transcript_text(detail).splitlines():
            normalized = line.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                lines.append(normalized)
    return "\n".join(lines)


def call_tencent_meeting_tool(name: str, arguments: dict[str, Any], timeout: int = 60) -> str:
    token = (settings.tencent_meeting_token or os.environ.get("TENCENT_MEETING_TOKEN", "")).strip()
    if not token:
        raise RuntimeError("TENCENT_MEETING_TOKEN 未配置")
    if not TENCENT_MEETING_SCRIPT.exists():
        raise RuntimeError("腾讯会议 skill 未安装")
    payload = {
        "name": name,
        "arguments": {
            **arguments,
            "_client_info": {"os": "macos", "agent": "codex-rom-ai", "model": "gpt-5-codex"},
        },
    }
    result = subprocess.run(
        ["python3", str(TENCENT_MEETING_SCRIPT), "tools/call", json.dumps(payload, ensure_ascii=False)],
        text=True,
        capture_output=True,
        timeout=timeout,
        env={**os.environ, "TENCENT_MEETING_TOKEN": token},
    )
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    response_error = _tencent_response_error(output)
    if response_error:
        raise RuntimeError(response_error)
    if result.returncode != 0 or "[错误]" in output:
        raise RuntimeError(output.strip() or "腾讯会议创建失败")
    return output


def schedule_tencent_meeting(subject: str, start_time: str, end_time: str) -> dict[str, str]:
    output = call_tencent_meeting_tool(
        "schedule_meeting",
        {
            "subject": subject,
            "start_time": start_time,
            "end_time": end_time,
            "time_zone": "Asia/Shanghai",
        },
    )
    return parse_tencent_meeting_result(output)


def build_tencent_records_query(meeting: models.Meeting) -> dict[str, Any]:
    metadata = extract_tencent_meeting_metadata(meeting)
    records_args: dict[str, Any] = {"page_size": 10}
    if metadata.get("meeting_id"):
        records_args["meeting_id"] = metadata["meeting_id"]
    elif metadata.get("meeting_code"):
        records_args["meeting_code"] = metadata["meeting_code"]
    elif meeting.date:
        start = meeting.date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = meeting.date.replace(hour=23, minute=59, second=59, microsecond=0)
        records_args["start_time"] = f"{start.isoformat()}+08:00"
        records_args["end_time"] = f"{end.isoformat()}+08:00"
    else:
        raise RuntimeError("会议卡片里没有腾讯会议号或会议时间，无法同步录制和转写")
    return records_args


def sync_tencent_meeting_minutes(db: Session, meeting: models.Meeting) -> models.Meeting:
    # 延迟导入避免循环依赖
    from app.services.context import deposit_meeting_transcript_to_knowledge
    # 通过包级命名空间调用，以便测试时 monkey-patch 生效
    import app.services as _svc

    meeting.sync_status = "syncing"
    meeting.sync_error = ""
    db.commit()
    records_args = build_tencent_records_query(meeting)
    records_text = _svc.call_tencent_meeting_tool("get_records_list", records_args)
    record = parse_tencent_record_result(records_text)
    records = record.get("records") or [record]
    if not any(item.get("record_file_id") for item in records):
        raise TencentMinutesUnavailableError("暂未查询到腾讯会议录制文件，请确认会议已结束并已开启云录制/转写")

    transcript = ""
    selected_record = record
    for candidate in records:
        record_file_id = candidate.get("record_file_id")
        if not record_file_id:
            continue
        try:
            transcript = fetch_complete_tencent_transcript(record_file_id)
        except Exception:
            transcript = ""
        if transcript:
            selected_record = candidate
            break
    if not transcript:
        raise TencentMinutesUnavailableError("腾讯会议转写暂未生成，请稍后再同步")

    meeting.transcript = transcript
    link_parts = [
        part
        for part in (meeting.recording_url or "").splitlines()
        if part.strip()
        and not part.strip().startswith("meeting_record_id")
        and not part.strip().startswith("record_file_id")
        and not part.strip().startswith("录制下载")
    ]
    if selected_record.get("meeting_record_id"):
        link_parts.append(f"meeting_record_id：{selected_record['meeting_record_id']}")
        address_text = _svc.call_tencent_meeting_tool(
            "get_record_addresses",
            {"meeting_record_id": selected_record["meeting_record_id"]},
        )
        address = parse_tencent_record_address_result(address_text)
        if address["view_address"]:
            link_parts.append(f"录屏查看：{address['view_address']}")
            meeting.recording_view_url = address["view_address"]
        if address["trace"]:
            link_parts.append(f"录屏 X-Tc-Trace：{address['trace']}")
        if address["rpc_uuid"]:
            link_parts.append(f"录屏 rpcUuid：{address['rpc_uuid']}")
        meeting.sync_trace_json = safe_json_dump(
            {"X-Tc-Trace": address["trace"], "rpcUuid": address["rpc_uuid"]},
            field_name="sync_trace_json",
        )
    record_file_id = selected_record.get("record_file_id", "")
    if record_file_id:
        link_parts.append(f"record_file_id：{record_file_id}")
        meeting.record_file_id = record_file_id
    if record.get("download_url"):
        link_parts.append(f"录制下载：{record['download_url']}")
    meeting.recording_url = "\n".join(part for part in link_parts if part).strip()
    meeting.status = "transcribed"
    meeting.sync_status = "synced"
    meeting.sync_error = ""
    meeting.last_synced_at = datetime.now()
    project = db.get(models.Project, meeting.project_id)
    if project:
        deposit_meeting_transcript_to_knowledge(db, project, meeting)
    db.commit()
    db.refresh(meeting)
    return meeting
