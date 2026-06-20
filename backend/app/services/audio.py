"""音频转写服务 - 支持 Whisper API 和 Mock 模式"""
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

from ..config import get_settings


@dataclass
class TranscriptionSegment:
    start: float  # 秒
    end: float
    text: str
    speaker: Optional[str] = None


@dataclass
class TranscriptionResult:
    text: str
    segments: list = field(default_factory=list)  # list[TranscriptionSegment]
    duration_seconds: float = 0.0
    source: str = "whisper"  # whisper / tencent / mock


async def transcribe_audio(file_path: str, provider: Optional[str] = None) -> TranscriptionResult:
    """转写音频文件，返回结构化结果"""
    settings = get_settings()
    provider = provider or settings.audio_provider

    if settings.mock_mode:
        return _transcribe_mock(file_path)

    if provider == "whisper":
        return await _transcribe_with_whisper(file_path)
    else:
        # 默认回退 mock
        return _transcribe_mock(file_path)


async def _transcribe_with_whisper(file_path: str) -> TranscriptionResult:
    """调用 OpenAI Whisper API 进行转写"""
    settings = get_settings()
    api_key = settings.whisper_api_key or settings.deepseek_api_key
    base_url = settings.whisper_base_url

    if not api_key:
        raise ValueError("未配置 whisper_api_key 或 deepseek_api_key，无法进行音频转写")

    url = f"{base_url.rstrip('/')}/audio/transcriptions"

    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(file_path, "rb") as audio_file:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (os.path.basename(file_path), audio_file)},
                data={
                    "model": "whisper-1",
                    "response_format": "verbose_json",
                    "language": "zh",
                },
            )

    if response.status_code != 200:
        raise RuntimeError(f"Whisper API 调用失败: {response.status_code} - {response.text[:500]}")

    data = response.json()

    # 解析 verbose_json 格式
    segments = []
    for seg in data.get("segments", []):
        segments.append(TranscriptionSegment(
            start=seg.get("start", 0),
            end=seg.get("end", 0),
            text=seg.get("text", "").strip(),
        ))

    return TranscriptionResult(
        text=data.get("text", ""),
        segments=segments,
        duration_seconds=data.get("duration", 0.0),
        source="whisper",
    )


def _transcribe_mock(file_path: str) -> TranscriptionResult:
    """Mock 模式返回示例转写结果"""
    filename = os.path.basename(file_path)
    return TranscriptionResult(
        text=(
            f"[Mock 转写结果 - {filename}]\n\n"
            "张总：这个项目的立面效果还是不够高级，需要再提升一下。\n"
            "李工：好的张总，我们会从材料质感和比例关系两个方向优化。\n"
            "张总：另外入口那里没有气势，要有仪式感。\n"
            "李工：明白，我们会加强入口序列的层次设计。\n"
            "张总：工期方面，下个月底之前要看到效果。\n"
        ),
        segments=[
            TranscriptionSegment(start=0, end=8, text="这个项目的立面效果还是不够高级，需要再提升一下。", speaker="张总"),
            TranscriptionSegment(start=8, end=15, text="好的张总，我们会从材料质感和比例关系两个方向优化。", speaker="李工"),
            TranscriptionSegment(start=15, end=22, text="另外入口那里没有气势，要有仪式感。", speaker="张总"),
            TranscriptionSegment(start=22, end=30, text="明白，我们会加强入口序列的层次设计。", speaker="李工"),
            TranscriptionSegment(start=30, end=38, text="工期方面，下个月底之前要看到效果。", speaker="张总"),
        ],
        duration_seconds=38.0,
        source="mock",
    )


def clean_transcript_text(raw_text: str) -> str:
    """清洗粘贴的转写文本：去空行、标准化时间戳、识别说话人"""
    lines = raw_text.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 标准化时间戳格式 (00:01:23 → [00:01:23])
        line = re.sub(r'^(\d{1,2}:\d{2}:\d{2})\s+', r'[\1] ', line)
        line = re.sub(r'^(\d{1,2}:\d{2})\s+', r'[\1] ', line)
        # 标准化说话人标记 (张总: → 张总：)，跳过已有时间戳前缀的行
        if not line.startswith('['):
            line = re.sub(r'^([^\s:：]{1,10})[:]\s*', r'\1：', line)
        cleaned.append(line)
    return "\n".join(cleaned)
