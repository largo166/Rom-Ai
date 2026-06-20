from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    triggers: tuple[str, ...]
    executor: str = "deepseek"
    retrieval_required: bool = False
    context_required: tuple[str, ...] = ("project_basic",)
    output_schema: tuple[str, ...] = ("markdown", "json")
    writeback: tuple[str, ...] = ("skill_card",)
    downstream: tuple[str, ...] = field(default_factory=tuple)


BUILTIN_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        id="brief_interpretation",
        name="任务书解读卡",
        description="从任务书或用户描述中抽取显性目标、隐性诉求、设计矛盾和切入点。",
        triggers=("任务书", "设计任务", "需求解读", "甲方要求", "设计要求"),
        retrieval_required=True,
        output_schema=("显性目标", "隐性目标", "设计矛盾", "切入点", "待补充信息"),
        downstream=("task_breakdown", "ppt_outline"),
    ),
    SkillDefinition(
        id="task_breakdown",
        name="任务拆解卡",
        description="把项目要求转成任务、责任角色、交付物和优先级。",
        triggers=("任务", "拆解", "分工", "排期", "待办", "工作计划"),
        output_schema=("tasks", "owners", "deliverables"),
        writeback=("skill_card", "tasks"),
    ),
    SkillDefinition(
        id="technical_focus",
        name="技术重点卡",
        description="提取日照、退界、面积、消防、报批等技术重点。",
        triggers=("技术", "重点", "日照", "退界", "面积", "消防", "规范", "报批"),
        retrieval_required=True,
        output_schema=("dimension", "risk", "checkpoints", "sources"),
    ),
    SkillDefinition(
        id="meeting_minutes",
        name="会议纪要卡",
        description="生成五段式纪要、甲方诉求转译、播报稿和会议待办。",
        triggers=("会议", "纪要", "转写", "待办", "决议", "腾讯会议", "播报", "甲方诉求"),
        retrieval_required=True,
        output_schema=("summary", "core_items", "demand_translation", "decisions", "todos", "broadcast_script"),
        writeback=("skill_card", "meeting", "tasks", "knowledge"),
    ),
    SkillDefinition(
        id="ppt_outline",
        name="PPT 大纲",
        description="生成面向业主汇报或内部评审的页面结构和汇报逻辑。",
        triggers=("ppt", "PPT", "汇报", "演示", "presentation", "框架", "大纲"),
        retrieval_required=True,
        output_schema=("title", "slides", "key_messages", "missing_assets"),
        downstream=("concept_copy", "image_prompt"),
    ),
    SkillDefinition(
        id="concept_copy",
        name="概念文字稿",
        description="基于项目语境生成概念标题、设计叙事、策略和汇报文字。",
        triggers=("概念", "文案", "文字稿", "叙事", "故事线", "设计主线"),
        retrieval_required=True,
        output_schema=("concept_title", "narrative", "strategies", "presentation_copy"),
        downstream=("ppt_outline", "image_prompt"),
    ),
    SkillDefinition(
        id="competitor_analysis",
        name="竞品分析",
        description="从历史项目和案例经验中提炼可迁移策略与适用边界。",
        triggers=("竞品", "对标", "类似项目", "案例", "可借鉴", "参考项目"),
        retrieval_required=True,
        output_schema=("comparables", "transferable_strategies", "limits", "risks"),
        downstream=("concept_copy", "scheme_review"),
    ),
    SkillDefinition(
        id="reference_image_classification",
        name="参考图分类",
        description="对手动上传或项目图片进行用途、风格、材料、空间和可复用点分类。",
        triggers=("参考图", "图片分类", "意向图", "素材", "风格图", "参考图片"),
        executor="vision_stub",
        output_schema=("image_type", "style_tags", "material_tags", "reuse_points", "next_prompt"),
        downstream=("image_prompt", "ai_image_generation"),
    ),
    SkillDefinition(
        id="image_prompt",
        name="AI 生图提示词",
        description="基于当前项目和参考图分类生成建筑意向图提示词。",
        triggers=("提示词", "生图提示", "prompt", "效果图提示", "立面提示"),
        retrieval_required=True,
        output_schema=("positive_prompt", "negative_prompt", "style_tags", "camera", "usage"),
        downstream=("ai_image_generation",),
    ),
    SkillDefinition(
        id="ai_image_generation",
        name="AI 生图",
        description="调用 Huashu/OpenAI-compatible 图片服务生成项目相关图片。",
        triggers=("生图", "生成图片", "效果图", "意向图", "立面图", "AI生图", "渲染"),
        executor="image_generation",
        retrieval_required=True,
        output_schema=("prompt", "image_paths", "provider", "model", "source_context"),
    ),
    SkillDefinition(
        id="scheme_review",
        name="方案评审",
        description="按任务书、技术重点、会议诉求和知识库经验检查当前方案。",
        triggers=("评审", "检查方案", "方案问题", "风险检查", "帮我看方案"),
        retrieval_required=True,
        output_schema=("strengths", "risks", "missing_info", "next_actions", "sources"),
    ),
)

SKILL_BY_ID = {skill.id: skill for skill in BUILTIN_SKILLS}


def list_builtin_skills() -> list[dict[str, object]]:
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "triggers": list(skill.triggers),
            "executor": skill.executor,
            "retrieval_required": skill.retrieval_required,
            "context_required": list(skill.context_required),
            "output_schema": list(skill.output_schema),
            "writeback": list(skill.writeback),
            "downstream": list(skill.downstream),
        }
        for skill in BUILTIN_SKILLS
    ]


def match_skill_by_keywords(text: str) -> tuple[SkillDefinition, float, str]:
    normalized = text.lower()
    best: tuple[SkillDefinition, float, str] | None = None
    for skill in BUILTIN_SKILLS:
        hits = [trigger for trigger in skill.triggers if trigger.lower() in normalized]
        if not hits:
            continue
        score = min(0.95, 0.58 + 0.12 * len(hits))
        reason = f"命中关键词：{', '.join(hits[:4])}"
        if best is None or score > best[1]:
            best = (skill, score, reason)
    if best:
        return best
    fallback = SKILL_BY_ID["task_breakdown"]
    return fallback, 0.35, "未命中明确技能，默认按任务拆解处理。"
