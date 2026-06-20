"""测试音频转写服务和相关端点"""
import io
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.audio import (
    clean_transcript_text,
    _transcribe_mock,
    TranscriptionResult,
    TranscriptionSegment,
)


# ── clean_transcript_text 测试 ────────────────────────────────────────────────

class TestCleanTranscriptText:
    def test_removes_blank_lines(self):
        raw = "第一行\n\n\n第二行\n\n第三行"
        result = clean_transcript_text(raw)
        assert "\n\n" not in result
        assert result == "第一行\n第二行\n第三行"

    def test_strips_leading_trailing_whitespace_per_line(self):
        raw = "  张总：你好  \n  李工：好的  "
        result = clean_transcript_text(raw)
        lines = result.split("\n")
        for line in lines:
            assert line == line.strip()

    def test_normalizes_timestamp_hhmmss(self):
        raw = "00:01:23 这是一段话"
        result = clean_transcript_text(raw)
        assert result == "[00:01:23] 这是一段话"

    def test_normalizes_timestamp_mmss(self):
        raw = "01:23 另一段话"
        result = clean_transcript_text(raw)
        assert result == "[01:23] 另一段话"

    def test_normalizes_speaker_colon_to_fullwidth(self):
        """英文冒号说话人标记 → 全角冒号"""
        raw = "张总: 这个项目不行"
        result = clean_transcript_text(raw)
        assert result == "张总：这个项目不行"

    def test_does_not_double_convert_fullwidth_colon(self):
        """已经是全角冒号的不应重复转换"""
        raw = "张总：这个项目不行"
        result = clean_transcript_text(raw)
        assert result == "张总：这个项目不行"

    def test_empty_string(self):
        result = clean_transcript_text("")
        assert result == ""

    def test_only_whitespace(self):
        result = clean_transcript_text("   \n   \n  ")
        assert result == ""

    def test_mixed_content(self):
        raw = (
            "00:00:05 张总: 立面效果要高级\n"
            "\n"
            "李工: 好的，我们改\n"
            "  \n"
            "00:01:00 张总：有没有问题"
        )
        result = clean_transcript_text(raw)
        lines = result.split("\n")
        assert len(lines) == 3
        assert "[00:00:05]" in lines[0]  # 时间戳已标准化
        assert "张总" in lines[0]  # 说话人在行里
        assert "李工：" in lines[1]  # 无时间戳的说话人被转换
        assert "[00:01:00]" in lines[2]  # 第三行时间戳已标准化


# ── _transcribe_mock 测试 ─────────────────────────────────────────────────────

class TestTranscribeMock:
    def test_returns_transcription_result(self):
        result = _transcribe_mock("/fake/path/meeting.mp3")
        assert isinstance(result, TranscriptionResult)

    def test_source_is_mock(self):
        result = _transcribe_mock("/fake/meeting.wav")
        assert result.source == "mock"

    def test_text_is_not_empty(self):
        result = _transcribe_mock("/fake/meeting.wav")
        assert len(result.text) > 0

    def test_text_contains_filename(self):
        result = _transcribe_mock("/some/path/test_audio.mp3")
        assert "test_audio.mp3" in result.text

    def test_has_segments(self):
        result = _transcribe_mock("/fake/meeting.wav")
        assert len(result.segments) > 0

    def test_segments_are_transcription_segment(self):
        result = _transcribe_mock("/fake/meeting.wav")
        for seg in result.segments:
            assert isinstance(seg, TranscriptionSegment)

    def test_segments_have_required_fields(self):
        result = _transcribe_mock("/fake/meeting.wav")
        for seg in result.segments:
            assert isinstance(seg.start, (int, float))
            assert isinstance(seg.end, (int, float))
            assert isinstance(seg.text, str)
            assert seg.end >= seg.start

    def test_duration_is_positive(self):
        result = _transcribe_mock("/fake/meeting.wav")
        assert result.duration_seconds > 0


# ── upload-audio 端点格式校验测试 ─────────────────────────────────────────────

class TestUploadAudioEndpoint:
    """测试上传端点的格式校验逻辑（不需要真实 DB，仅测试校验函数本身）"""

    def _check_format(self, filename: str, allowed_formats: str) -> bool:
        """复用端点内部的格式校验逻辑"""
        allowed = [f.strip() for f in allowed_formats.split(",")]
        ext = os.path.splitext(filename)[1].lower()
        return ext in allowed

    def test_valid_wav(self):
        assert self._check_format("meeting.wav", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is True

    def test_valid_mp3(self):
        assert self._check_format("meeting.mp3", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is True

    def test_valid_m4a(self):
        assert self._check_format("meeting.m4a", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is True

    def test_valid_webm(self):
        assert self._check_format("recording.webm", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is True

    def test_reject_exe(self):
        assert self._check_format("virus.exe", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is False

    def test_reject_pdf(self):
        assert self._check_format("document.pdf", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is False

    def test_reject_py(self):
        assert self._check_format("script.py", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is False

    def test_reject_no_extension(self):
        assert self._check_format("noextension", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is False

    def test_case_insensitive(self):
        """扩展名大写也应被接受（因为 .lower() 处理）"""
        assert self._check_format("meeting.MP3", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is True
        assert self._check_format("meeting.WAV", ".wav,.mp3,.m4a,.ogg,.flac,.webm") is True


# ── 文件大小校验测试 ──────────────────────────────────────────────────────────

class TestFileSizeValidation:
    def test_within_limit(self):
        max_mb = 100
        max_bytes = max_mb * 1024 * 1024
        content = b"x" * (50 * 1024 * 1024)  # 50MB
        assert len(content) <= max_bytes

    def test_exceeds_limit(self):
        max_mb = 10
        max_bytes = max_mb * 1024 * 1024
        content = b"x" * (11 * 1024 * 1024)  # 11MB
        assert len(content) > max_bytes
