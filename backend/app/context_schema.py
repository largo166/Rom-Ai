"""上下文包 schema 常量 — 唯一来源"""
from enum import Enum

SCHEMA_VERSION = "1.0"


class ContextType(str, Enum):
    project_context = "project_context"
    meeting_summary = "meeting_summary"
    meeting_transcript = "meeting_transcript"
    case_strategy = "case_strategy"
    method = "method"
    strategy = "strategy"
    designer_profile = "designer_profile"
    agent_skill = "agent_skill"


TYPE_ALIASES = {
    "project_deposit": ContextType.project_context,
    "method_template": ContextType.method,
    "obsidian_candidate": ContextType.project_context,
}

STANDARD_FRONTMATTER_FIELDS = [
    "type", "title", "description", "resource", "tags", "timestamp", "schema_version"
]
