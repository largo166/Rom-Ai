"""
AI代理 Orchestrator
用户输入 → 意图分类 → 匹配Skill → 读项目上下文 → 执行 → 成果卡
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Skill Manifest（统一结构注册表）
SKILL_MANIFEST = [
    {
        "id": "brief_interpretation",
        "name": "任务书解读",
        "trigger": ["任务书", "解读", "brief", "设计条件", "项目要求"],
        "context_required": ["project_basic", "project_files"],
        "output_schema": "brief_analysis",
        "executor": "deepseek",
        "writeback": ["project_report", "knowledge"],
        "retrieval_required": False,
        "description": "解读项目任务书，提取关键设计条件、约束和目标",
    },
    {
        "id": "task_breakdown",
        "name": "任务拆解",
        "trigger": ["任务拆解", "工作分解", "拆分", "计划", "排期"],
        "context_required": ["project_basic", "project_tasks"],
        "output_schema": "task_list",
        "executor": "deepseek",
        "writeback": ["project_tasks"],
        "retrieval_required": False,
        "description": "将项目目标拆解为可执行的任务清单",
    },
    {
        "id": "technical_focus",
        "name": "技术重点",
        "trigger": ["技术重点", "技术难点", "关键技术", "技术方案"],
        "context_required": ["project_basic", "project_files"],
        "output_schema": "technical_points",
        "executor": "deepseek",
        "writeback": ["project_report"],
        "retrieval_required": False,
        "description": "识别项目技术重点和难点，提出应对策略",
    },
    {
        "id": "meeting_minutes",
        "name": "会议纪要",
        "trigger": ["会议", "纪要", "转写", "meeting", "记录"],
        "context_required": ["project_basic", "project_meetings"],
        "output_schema": "five_section_minutes",
        "executor": "deepseek",
        "writeback": ["meeting", "project_tasks", "knowledge"],
        "retrieval_required": False,
        "description": "生成五段式会议纪要并转译甲方诉求",
    },
    {
        "id": "ppt_outline",
        "name": "PPT大纲",
        "trigger": ["PPT", "汇报", "演示", "大纲", "报告结构"],
        "context_required": ["project_basic", "project_files", "project_reports"],
        "output_schema": "ppt_structure",
        "executor": "deepseek",
        "writeback": ["project_report"],
        "retrieval_required": False,
        "description": "生成项目汇报PPT的叙事大纲和页面结构",
    },
    {
        "id": "concept_copy",
        "name": "概念文字稿",
        "trigger": ["概念", "文字稿", "设计说明", "理念", "concept"],
        "context_required": ["project_basic", "project_reports"],
        "output_schema": "concept_text",
        "executor": "deepseek",
        "writeback": ["project_report", "knowledge"],
        "retrieval_required": False,
        "description": "基于项目研判生成设计概念文字稿",
    },
    {
        "id": "image_prompt",
        "name": "生图提示词",
        "trigger": ["生图", "提示词", "prompt", "效果图", "意向图"],
        "context_required": ["project_basic"],
        "output_schema": "image_prompts",
        "executor": "deepseek",
        "writeback": ["skill_card"],
        "retrieval_required": False,
        "description": "生成AI生图的提示词（中英文），暂不接生图API",
    },
    {
        "id": "competitor_analysis",
        "name": "竞品分析",
        "trigger": ["竞品", "对标", "竞争", "类似项目"],
        "context_required": ["project_basic"],
        "output_schema": "competitor_report",
        "executor": "deepseek",
        "writeback": ["project_report", "knowledge"],
        "retrieval_required": True,
        "description": "分析竞品项目，提取可迁移策略（依赖检索）",
    },
]

# Executor Registry
EXECUTOR_REGISTRY = {
    "deepseek": "text_executor",
    "vision_stub": "vision_executor",
    "image_generation": "image_executor",
}


class Orchestrator:
    """AI代理调度器"""

    def __init__(self, skills: Optional[List[Dict]] = None):
        self.skills = skills or SKILL_MANIFEST

    def match_skill_by_keywords(self, user_input: str) -> Optional[Dict]:
        """关键词快速通道匹配"""
        input_lower = user_input.lower()
        best_match = None
        best_score = 0

        for skill in self.skills:
            score = sum(1 for kw in skill["trigger"] if kw.lower() in input_lower)
            if score > best_score:
                best_score = score
                best_match = skill

        return best_match if best_score > 0 else None

    def build_intent_prompt(self, user_input: str, project_context: Dict) -> str:
        """构建意图分类 Prompt（发给DeepSeek）"""
        skill_list = "\n".join(
            [f"- {s['id']}: {s['name']} - {s['description']}" for s in self.skills]
        )

        return f"""你是建筑设计AI助手的意图分类器。用户在项目"{project_context.get('name', '')}"的上下文中说了一句话，请判断用户意图并匹配最合适的技能。

## 可用技能列表
{skill_list}

## 项目上下文
- 名称：{project_context.get('name', '')}
- 城市：{project_context.get('city', '')}
- 类型：{project_context.get('project_type', '')}
- 阶段：{project_context.get('stage', '')}

## 用户输入
{user_input}

## 输出要求（严格JSON，不输出任何Markdown包装）
{{
  "intent": "匹配的skill id，如果无法匹配则为 'general_chat'",
  "confidence": 0.0到1.0的置信度,
  "reason": "匹配理由（一句话）",
  "needs_clarification": false,
  "clarification_question": ""
}}

注意：
- confidence < 0.5 时设 needs_clarification=true 并给出澄清问题
- 如果用户只是闲聊/问好，intent="general_chat"
- 优先匹配最相关的技能"""

    def build_skill_execution_prompt(
        self,
        skill: Dict,
        user_input: str,
        project_context: Dict,
        additional_context: str = "",
    ) -> str:
        """构建技能执行 Prompt"""
        base_ctx = f"""项目：{project_context.get('name', '')}（{project_context.get('city', '')}，{project_context.get('project_type', '')}）
阶段：{project_context.get('stage', '')}
用户需求：{user_input}
"""
        if additional_context:
            base_ctx += f"\n补充上下文：\n{additional_context}\n"

        prompts: Dict[str, str] = {
            "brief_interpretation": f"""你是建筑设计项目顾问。请基于以下项目上下文和用户需求，对项目任务书进行深度解读。

{base_ctx}

请输出JSON（不加Markdown包装）：
{{
  "project_positioning": "项目定位判断",
  "design_conditions": ["关键设计条件1", "条件2"],
  "constraints": ["约束1", "约束2"],
  "targets": ["目标1", "目标2"],
  "hidden_demands": ["隐性需求1"],
  "contradictions": ["矛盾点1"],
  "strategy_suggestion": "策略建议"
}}""",
            "task_breakdown": f"""你是项目管理助手。请将以下项目目标拆解为可执行任务。

{base_ctx}

请输出JSON（不加Markdown包装）：
{{
  "tasks": [
    {{"title": "任务名", "description": "说明", "priority": "high/medium/low", "estimated_days": 3, "dependencies": []}}
  ],
  "critical_path": ["关键路径任务1", "任务2"],
  "risks": ["风险1"]
}}""",
            "technical_focus": f"""你是建筑技术顾问。请识别项目技术重点。

{base_ctx}

请输出JSON（不加Markdown包装）：
{{
  "key_technical_points": [
    {{"point": "技术重点", "challenge": "难点", "strategy": "应对策略", "priority": "high/medium/low"}}
  ],
  "recommended_references": ["参考建议1"]
}}""",
            "meeting_minutes": f"""你是会议纪要助手。请为项目生成五段式会议纪要。

{base_ctx}

请输出JSON（不加Markdown包装）：
{{
  "meeting_background": "会议背景",
  "decisions": ["决策1", "决策2"],
  "action_items": [{{"task": "任务", "owner": "负责人", "deadline": "截止时间"}}],
  "open_issues": ["待解决问题1"],
  "next_steps": ["下一步1"],
  "client_demands": ["甲方诉求转译1"]
}}""",
            "ppt_outline": f"""你是汇报策略师。请为项目汇报生成PPT大纲。

{base_ctx}

请输出JSON（不加Markdown包装）：
{{
  "narrative_line": "汇报主线（一句话）",
  "sections": [
    {{"title": "章节标题", "pages": 3, "key_content": ["要点1"], "visual_suggestion": "视觉建议"}}
  ],
  "opening_hook": "开场设计",
  "closing_impact": "结尾设计"
}}""",
            "concept_copy": f"""你是建筑设计文案师。请生成项目设计概念文字稿。

{base_ctx}

请输出JSON（不加Markdown包装）：
{{
  "concept_title": "概念名称",
  "core_idea": "核心理念（一段话）",
  "design_narrative": "设计叙事（3-5段，保留设计语言美感）",
  "keywords": ["关键词1", "关键词2"],
  "spatial_strategy": "空间策略描述"
}}""",
            "image_prompt": f"""你是AI生图提示词专家。请为建筑设计项目生成高质量生图提示词。

{base_ctx}

请输出JSON（不加Markdown包装）：
{{
  "prompts": [
    {{
      "scene": "场景描述",
      "prompt_cn": "中文提示词",
      "prompt_en": "English prompt for AI image generation",
      "style": "风格标签",
      "negative_prompt": "negative prompt"
    }}
  ]
}}""",
            "competitor_analysis": f"""你是竞品分析师。请分析与当前项目相关的竞品。

{base_ctx}

请输出JSON（不加Markdown包装）：
{{
  "competitors": [
    {{"name": "项目名", "location": "城市", "similarity": "相似点", "transferable": "可迁移策略", "non_transferable": "不可照搬的", "risk": "风险"}}
  ],
  "summary": "竞品分析总结",
  "recommendations": ["建议1"]
}}""",
        }

        return prompts.get(
            skill["id"],
            f"你是建筑设计项目助手。请回答用户问题（必须基于当前项目背景）：\n{base_ctx}",
        )

    def format_result_card(
        self,
        skill: Dict,
        result: Any,
        project_context: Dict,
        user_input: str,
    ) -> Dict[str, Any]:
        """格式化为成果卡"""
        return {
            "card_type": skill["id"],
            "skill_name": skill["name"],
            "title": f"{skill['name']} - {project_context.get('name', '')}",
            "status": "generated",
            "context_used": {
                "project": project_context.get("name", ""),
                "stage": project_context.get("stage", ""),
                "user_input": user_input[:100],
            },
            "result": result,
            "actions": ["view", "copy", "writeback", "deepen"],
            "suggested_next": self._get_suggested_next(skill["id"]),
            "generated_at": datetime.now().isoformat(),
            "sources": [],  # Phase 6 RAG 接通后填充
        }

    def _get_suggested_next(self, skill_id: str) -> List[Dict[str, str]]:
        """建议下一步（多Skill关系）"""
        next_map: Dict[str, List[Dict[str, str]]] = {
            "brief_interpretation": [
                {"skill": "task_breakdown", "label": "拆解任务"},
                {"skill": "technical_focus", "label": "识别技术重点"},
            ],
            "task_breakdown": [
                {"skill": "ppt_outline", "label": "生成汇报大纲"},
            ],
            "ppt_outline": [
                {"skill": "concept_copy", "label": "写概念文字稿"},
                {"skill": "image_prompt", "label": "生成配图提示词"},
            ],
            "concept_copy": [
                {"skill": "image_prompt", "label": "生成配图提示词"},
            ],
            "image_prompt": [],
            "meeting_minutes": [
                {"skill": "task_breakdown", "label": "拆解待办为任务"},
            ],
            "technical_focus": [
                {"skill": "competitor_analysis", "label": "竞品分析"},
            ],
        }
        return next_map.get(skill_id, [])
