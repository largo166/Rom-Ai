"""
AI 生图 Provider
支持 OpenAI-compatible API（huashu默认，可通过配置切换）
Key 只从本机 .env 配置读取，绝不写进源码
"""
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ImageGenerationResult:
    """生图结果容器"""

    def __init__(
        self,
        success: bool,
        image_path: str = "",
        error: str = "",
        prompt_used: str = "",
        model: str = "",
        metadata: Optional[Dict] = None,
    ):
        self.success = success
        self.image_path = image_path
        self.error = error
        self.prompt_used = prompt_used
        self.model = model
        self.metadata: Dict[str, Any] = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "image_path": self.image_path,
            "error": self.error,
            "prompt_used": self.prompt_used,
            "model": self.model,
            "metadata": self.metadata,
        }


class ImageGenerationProvider:
    """
    OpenAI-compatible 生图接口封装
    默认 provider: huashu
    可通过 .env 中 IMAGE_BASE_URL / IMAGE_MODEL / IMAGE_PROVIDER 切换
    """

    def __init__(self) -> None:
        self.api_key: str = settings.image_api_key
        self.base_url: str = (
            getattr(settings, "image_base_url", "")
            or "https://api.huashu.ai/v1"
        )
        self.model: str = (
            getattr(settings, "image_model", "") or "huashu-xl"
        )
        self.provider: str = (
            getattr(settings, "image_provider", "") or "huashu"
        )

    @property
    def is_configured(self) -> bool:
        """是否已配置 API Key"""
        return bool(self.api_key and self.api_key.strip())

    def get_status(self) -> Dict[str, Any]:
        """返回当前配置状态（供 /api/image-provider/status 使用）"""
        url_display = (
            self.base_url[:50] + "..."
            if len(self.base_url) > 50
            else self.base_url
        )
        return {
            "configured": self.is_configured,
            "provider": self.provider,
            "model": self.model,
            "base_url": url_display,
        }

    async def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
        style: str = "natural",
    ) -> ImageGenerationResult:
        """
        调用生图 API。
        未配置时返回友好错误，绝不伪造图片数据。
        """
        if not self.is_configured:
            return ImageGenerationResult(
                success=False,
                error="not_configured",
                prompt_used=prompt,
                metadata={
                    "message": (
                        "AI生图未配置。请在 .env 文件中设置 IMAGE_API_KEY "
                        "（以及可选的 IMAGE_BASE_URL / IMAGE_MODEL / IMAGE_PROVIDER）。"
                    )
                },
            )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/images/generations",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "size": size,
                        "quality": quality,
                        "n": n,
                        "style": style,
                        "response_format": "b64_json",
                    },
                )

                if response.status_code != 200:
                    error_msg = response.text[:500]
                    logger.error(
                        "Image API error %s: %s", response.status_code, error_msg
                    )
                    return ImageGenerationResult(
                        success=False,
                        error="api_error",
                        prompt_used=prompt,
                        metadata={
                            "status_code": response.status_code,
                            "message": error_msg,
                        },
                    )

                data = response.json()
                image_data = data.get("data", [{}])[0]
                b64 = image_data.get("b64_json", "")

                if not b64:
                    return ImageGenerationResult(
                        success=False,
                        error="no_image_data",
                        prompt_used=prompt,
                        metadata={"message": "API返回中无图片数据（b64_json为空）"},
                    )

                return ImageGenerationResult(
                    success=True,
                    prompt_used=prompt,
                    model=self.model,
                    metadata={
                        "b64_json": b64,
                        "size": size,
                        "quality": quality,
                        "style": style,
                        "revised_prompt": image_data.get("revised_prompt", ""),
                    },
                )

        except httpx.TimeoutException:
            return ImageGenerationResult(
                success=False,
                error="timeout",
                prompt_used=prompt,
                metadata={"message": "生图请求超时（60秒），请稍后重试"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Image generation failed: %s", exc)
            return ImageGenerationResult(
                success=False,
                error="unknown",
                prompt_used=prompt,
                metadata={"message": str(exc)},
            )

    def save_image(
        self,
        b64_data: str,
        project_id: str,
        output_dir: Optional[Path] = None,
        filename_prefix: str = "ai_gen",
    ) -> Optional[str]:
        """
        将 base64 图片解码并保存到项目成果目录。
        返回保存路径字符串；失败返回 None。
        """
        if not b64_data:
            return None

        # 确定输出目录（优先级：参数传入 > 配置 > 项目默认）
        if output_dir:
            save_dir = output_dir
        elif settings.image_output_dir:
            save_dir = Path(settings.image_output_dir)
        else:
            save_dir = (
                settings.data_dir_path
                / "projects"
                / str(project_id)
                / "assets"
                / "ai-generated"
            )

        save_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.png"
        filepath = save_dir / filename

        try:
            image_bytes = base64.b64decode(b64_data)
            filepath.write_bytes(image_bytes)
            logger.info("Image saved: %s", filepath)
            return str(filepath)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to save image: %s", exc)
            return None


class ReferenceImageClassifier:
    """
    参考图分类器
    v1：手动上传/标签 + DeepSeek 生成结构化说明
    视觉自动分类预留 VisionProvider 接缝（future）
    """

    # 受控分类词表（与知识库 metadata 共用同一套）
    STYLE_VOCAB: List[str] = [
        "现代简约", "新中式", "工业风", "极简", "未来科技",
        "自然生态", "古典欧式", "东南亚", "北欧", "日式禅意",
        "解构主义", "参数化", "地域性", "可持续", "其他",
    ]

    MATERIAL_VOCAB: List[str] = [
        "玻璃幕墙", "石材", "金属", "木材", "混凝土",
        "砖", "竹", "膜结构", "陶板", "GRC", "其他",
    ]

    ELEMENT_VOCAB: List[str] = [
        "立面", "入口", "中庭", "屋顶", "景观",
        "室内", "细部", "鸟瞰", "剖面", "概念图", "其他",
    ]

    def classify_manual(
        self,
        tags: List[str],
        description: str = "",
    ) -> Dict[str, Any]:
        """手动分类（v1 默认方式）：将标签对应到受控词表"""
        matched_styles = [t for t in tags if t in self.STYLE_VOCAB]
        matched_materials = [t for t in tags if t in self.MATERIAL_VOCAB]
        matched_elements = [t for t in tags if t in self.ELEMENT_VOCAB]

        return {
            "styles": matched_styles or ["其他"],
            "materials": matched_materials,
            "elements": matched_elements or ["其他"],
            "description": description,
            "classification_method": "manual",
            "confidence": 1.0,
        }

    def build_description_prompt(
        self,
        project_context: Dict[str, Any],
        user_description: str = "",
    ) -> str:
        """构建 DeepSeek 图片说明生成 Prompt"""
        styles_hint = ", ".join(self.STYLE_VOCAB[:8])
        materials_hint = ", ".join(self.MATERIAL_VOCAB[:8])
        elements_hint = ", ".join(self.ELEMENT_VOCAB[:8])
        return (
            f"你是建筑设计参考图分析师。请为用户上传的参考图生成结构化说明。\n\n"
            f"项目：{project_context.get('name', '')}（{project_context.get('project_type', '')}）\n"
            f"用户备注：{user_description}\n\n"
            f"请输出JSON：\n"
            f"{{\n"
            f'  "description": "图片内容描述（50字以内）",\n'
            f'  "design_value": "对当前项目的参考价值（一句话）",\n'
            f'  "suggested_styles": ["从以下选：{styles_hint}"],\n'
            f'  "suggested_materials": ["从以下选：{materials_hint}"],\n'
            f'  "suggested_elements": ["从以下选：{elements_hint}"]\n'
            f"}}"
        )

    @staticmethod
    def get_vocabularies() -> Dict[str, List[str]]:
        """返回受控词表（供前端下拉列表使用）"""
        return {
            "styles": ReferenceImageClassifier.STYLE_VOCAB,
            "materials": ReferenceImageClassifier.MATERIAL_VOCAB,
            "elements": ReferenceImageClassifier.ELEMENT_VOCAB,
        }
