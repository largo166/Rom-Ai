"""AI image prompt templating for project skill cards."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app import models


DEFAULT_IMAGE_TEMPLATE = (
    "基于{project_name}生成一张{view}建筑方案概念图。"
    "项目关键词：{keywords}。"
    "设计方向：{strategy}。"
    "风格控制：真实建筑表达、方案汇报级、材料和尺度可信、空间关系清晰。"
    "要求：不要文字水印，不要过度幻想，不要畸形透视，适合建筑设计前期多方案比较。"
)

DEFAULT_VIEWS = ["总体鸟瞰", "入口人视", "庭院空间", "立面细节"]
DOMAIN_KEYWORDS = [
    "宋式",
    "抬板",
    "坞壁",
    "院落",
    "展示区",
    "入口",
    "檐口",
    "石材",
    "灰空间",
    "仪式感",
    "日照",
    "退距",
    "石家庄",
]


@dataclass
class PromptVariant:
    view: str
    prompt: str


def extract_image_keywords(project: models.Project, user_prompt: str = "", sources: list[dict[str, Any]] | None = None) -> list[str]:
    text_parts = [
        project.name or "",
        project.city or "",
        project.project_type or "",
        project.phase or "",
        project.description or "",
        project.client_demands or "",
        user_prompt or "",
    ]
    for source in sources or []:
        text_parts.append(str(source.get("quote") or ""))
        text_parts.append(str(source.get("source_file") or ""))
    text = "\n".join(text_parts)

    keywords: list[str] = []
    for item in DOMAIN_KEYWORDS:
        if item and item in text and item not in keywords:
            keywords.append(item)
    # Add stable project metadata even when not present in source snippets.
    for item in [project.city, project.project_type, project.phase]:
        if item and item.strip() and item.strip() not in keywords:
            keywords.append(item.strip())

    # Pick a few Chinese noun-ish phrases from explicit user prompt.
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", user_prompt or ""):
        if token not in keywords and not token.isdigit():
            keywords.append(token)
        if len(keywords) >= 12:
            break
    return keywords[:12] or [project.name or "建筑项目", "方案前期", "真实建筑表达"]


def build_multiview_image_prompts(
    project: models.Project,
    *,
    user_prompt: str = "",
    sources: list[dict[str, Any]] | None = None,
    template: str = DEFAULT_IMAGE_TEMPLATE,
    views: list[str] | None = None,
) -> dict[str, Any]:
    keywords = extract_image_keywords(project, user_prompt, sources)
    strategy = user_prompt.strip() or "结合项目定位、历史经验和甲方诉求进行多视角概念探索"
    variants = []
    for view in (views or DEFAULT_VIEWS)[:4]:
        variants.append(
            {
                "view": view,
                "prompt": template.format(
                    project_name=project.name or "当前项目",
                    view=view,
                    keywords="、".join(keywords),
                    strategy=strategy,
                ),
            }
        )
    return {
        "template_id": "rmo-architectural-multiview-v1",
        "keywords": keywords,
        "views": [item["view"] for item in variants],
        "prompt_variants": variants,
    }
