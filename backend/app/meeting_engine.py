"""
会议纪要引擎：五段式纪要 + 甲方诉求转译 + 播报脚本
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# 种子黑话词典（甲方常见表达 → 设计语言转译）
SEED_JARGON_DICT = {
    "不够高级": ["材料档次提升", "比例精细化", "留白增加", "细节品质感"],
    "太普通": ["辨识度不足", "需要记忆点/标志性元素", "形式语言需强化"],
    "感觉不对": ["设计逻辑未对齐甲方预期", "需要回溯任务书核心诉求"],
    "大气一点": ["尺度感放大", "入口/大堂/中庭空间加强", "轴线感/仪式感"],
    "大气": ["尺度感放大", "入口/大堂/中庭空间加强", "轴线感/仪式感"],
    "现代感": ["简洁线条", "玻璃/金属/石材组合", "虚实对比", "去装饰化"],
    "有文化": ["在地性表达", "地域符号抽象化", "叙事性空间"],
    "接地气": ["功能优先", "运营可行性", "成本可控", "市场验证过的方案"],
    "国际范": ["对标国际案例", "简约克制", "材料高级感", "品牌调性"],
    "要有亮点": ["需要一个核心记忆点", "可传播的设计概念", "差异化卖点"],
    "太贵了": ["控制幕墙面积", "优化结构体系", "标准化构件", "分期实施"],
    "快一点": ["压缩设计周期", "优先出关键节点成果", "并行作业"],
    "跟XX项目学学": ["对标竞品分析", "提取可迁移策略", "但需差异化"],
    "没有特色": ["需要差异化设计语言", "辨识度不足", "形式记忆点缺失"],
    "太保守": ["方案创新度不够", "需突破常规形态", "建议参考前沿案例"],
    "高端": ["材料选用A级", "空间尺度感强", "细节处理精致", "品牌溢价感"],
    "有品位": ["设计克制有内涵", "避免过度装饰", "空间叙事完整"],
    "接地": ["成本控制优先", "本地材料使用", "施工可行性强"],
    "简洁": ["去繁就简", "减少构件层次", "纯净立面语言"],
    "丰富": ["立面层次增加", "材料多样化", "功能复合化"],
}


class MeetingMinutesEngine:
    """会议纪要处理引擎"""

    def __init__(self, jargon_dict: Optional[Dict[str, List[str]]] = None):
        self.jargon_dict = jargon_dict or SEED_JARGON_DICT

    def generate_five_section_minutes(
        self,
        transcript: str,
        project_context: Optional[Dict[str, Any]] = None,
        ai_response: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        生成五段式纪要结构
        如果有 ai_response（来自 DeepSeek），直接结构化；否则返回空模板待填充
        """
        template: Dict[str, Any] = {
            "meeting_content": "",       # 纪要内容（全文摘要）
            "key_items": [],             # 核心事项 [{item, priority, owner}]
            "client_translation": [],    # 甲方诉求转译 [{original, timestamp, translation, confidence, source_quote}]
            "decisions": [],             # 会议决议 [{decision, responsible, deadline}]
            "action_items": [],          # 待办事项 [{task, assignee, due_date, priority}]
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "version": 1,
                "status": "draft",       # draft/reviewed/final
                "is_internal": True,     # 内部版含转译
            },
        }

        if ai_response:
            template["meeting_content"] = ai_response.get("summary", "")
            template["key_items"] = ai_response.get("key_items", [])
            template["client_translation"] = ai_response.get("client_translation", [])
            template["decisions"] = ai_response.get("decisions", [])
            template["action_items"] = ai_response.get("action_items", [])

        return template

    def translate_client_demands(
        self,
        transcript: str,
        existing_translations: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """
        基于种子词典进行甲方诉求初步转译（规则层）
        AI 补充在调用方处理
        """
        translations: List[Dict[str, Any]] = []
        lines = transcript.split("\n")

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            for jargon, meanings in self.jargon_dict.items():
                if jargon in line_stripped:
                    translations.append(
                        {
                            "original": line_stripped,
                            "timestamp": f"line_{i + 1}",
                            "jargon_matched": jargon,
                            "translation": meanings,
                            "confidence": 0.8,
                            "source": "seed_dictionary",
                            "source_quote": line_stripped[:100],
                        }
                    )

        return translations

    def generate_broadcast_script(self, minutes: Dict[str, Any]) -> str:
        """
        生成口语化播报脚本（核心事项+决议+待办）
        不朗读 Markdown 原文
        """
        parts: List[str] = []

        parts.append("以下是本次会议要点播报：")

        key_items = minutes.get("key_items", [])
        if key_items:
            parts.append("\n【核心事项】")
            for i, item in enumerate(key_items[:5], 1):
                text = item.get("item", item) if isinstance(item, dict) else str(item)
                parts.append(f"第{i}项：{text}")

        decisions = minutes.get("decisions", [])
        if decisions:
            parts.append("\n【会议决议】")
            for i, dec in enumerate(decisions[:5], 1):
                text = dec.get("decision", dec) if isinstance(dec, dict) else str(dec)
                parts.append(f"决议{i}：{text}")

        actions = minutes.get("action_items", [])
        if actions:
            parts.append("\n【待办事项】")
            for i, action in enumerate(actions[:5], 1):
                task = action.get("task", action) if isinstance(action, dict) else str(action)
                assignee = action.get("assignee", "") if isinstance(action, dict) else ""
                if assignee:
                    parts.append(f"待办{i}：{task}，负责人{assignee}")
                else:
                    parts.append(f"待办{i}：{task}")

        parts.append("\n播报结束。")
        return "\n".join(parts)

    def split_internal_external(self, minutes: Dict[str, Any]) -> Dict[str, Any]:
        """
        分离内部版（含转译）和对外版（不含转译）
        """
        external = {
            "meeting_content": minutes.get("meeting_content", ""),
            "key_items": minutes.get("key_items", []),
            "decisions": minutes.get("decisions", []),
            "action_items": minutes.get("action_items", []),
            "metadata": {
                **minutes.get("metadata", {}),
                "is_internal": False,
            },
        }

        internal = {
            **minutes,
            "metadata": {**minutes.get("metadata", {}), "is_internal": True},
        }

        return {"internal": internal, "external": external}


def build_minutes_prompt(transcript: str, project_context: Optional[Dict] = None) -> str:
    """
    构建发给 DeepSeek 的会议纪要生成 Prompt
    """
    context_str = ""
    if project_context:
        context_str = f"""
项目背景：
- 项目名称：{project_context.get('name', '未知')}
- 城市：{project_context.get('city', '未知')}
- 类型：{project_context.get('project_type', '未知')}
- 阶段：{project_context.get('stage', project_context.get('phase', '未知'))}
- 甲方：{project_context.get('client_name', '未知')}
"""

    prompt = f"""你是建筑设计项目的会议纪要助手。请基于以下会议转写文本，生成五段式结构化纪要。

{context_str}

## 输出要求（严格 JSON 格式）

请输出以下 JSON 结构，不要包含 markdown 代码块标记：
{{
  "summary": "会议整体摘要（200字以内）",
  "key_items": [
    {{"item": "核心事项描述", "priority": "high/medium/low", "owner": "负责人"}}
  ],
  "client_translation": [
    {{
      "original": "甲方原话",
      "timestamp": "时间点或行号",
      "translation": ["设计语言转译1", "转译2"],
      "confidence": 0.8,
      "source_quote": "转写稿中的原文片段"
    }}
  ],
  "decisions": [
    {{"decision": "决议内容", "responsible": "负责人", "deadline": "截止日期或空字符串"}}
  ],
  "action_items": [
    {{"task": "待办描述", "assignee": "负责人", "due_date": "日期或空字符串", "priority": "high/medium/low"}}
  ]
}}

## 转译规则
- 每条转译必须锚定转写原话
- 甲方说"不够高级"→可能指材料/比例/留白
- 甲方说"大气"→尺度感/仪式感/轴线
- 甲方说"现代感"→简洁/玻璃金属/虚实对比
- 低置信度的转译标 confidence < 0.6
- 如果转写中没有明显甲方诉求，client_translation 可为空数组

## 会议转写文本

{transcript}
"""
    return prompt
