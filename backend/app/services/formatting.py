"""Markdown 格式标准化"""
import re
from datetime import datetime
from typing import Optional


def standardize_markdown(content: str, title: str, file_type: str = "文档") -> str:
    """标准化 Markdown 文件内容"""
    lines = content.split("\n")

    # 1. 确保有 frontmatter
    has_frontmatter = lines[0].strip() == "---" if lines else False
    if has_frontmatter:
        end_idx = _find_frontmatter_end(lines)
        if end_idx > 0:
            # 更新已有 frontmatter
            frontmatter = _update_frontmatter(lines[1:end_idx], title, file_type)
            body = "\n".join(lines[end_idx + 1:])
        else:
            frontmatter = _build_frontmatter(title, file_type)
            body = content
    else:
        frontmatter = _build_frontmatter(title, file_type)
        body = content

    # 2. 确保 body 有一级标题
    body = _ensure_heading(body, title)

    # 3. 规范化空行（连续空行压缩为1个）
    body = re.sub(r'\n{3,}', '\n\n', body)

    # 4. 规范化列表缩进（统一2空格）
    body = _normalize_list_indent(body)

    return f"---\n{frontmatter}\n---\n\n{body.strip()}\n"


def _build_frontmatter(title: str, file_type: str) -> str:
    date = datetime.now().strftime("%Y-%m-%d")
    return f"type: {file_type}\ntitle: {title}\ndate: {date}"


def _update_frontmatter(lines: list, title: str, file_type: str) -> str:
    """保留已有字段，补充缺失字段"""
    fields: dict = {}
    for line in lines:
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()
    if "type" not in fields:
        fields["type"] = file_type
    if "title" not in fields:
        fields["title"] = title
    if "date" not in fields:
        fields["date"] = datetime.now().strftime("%Y-%m-%d")
    return "\n".join(f"{k}: {v}" for k, v in fields.items())


def _find_frontmatter_end(lines: list) -> int:
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return -1


def _ensure_heading(body: str, title: str) -> str:
    """确保正文有一级标题"""
    stripped = body.lstrip()
    if stripped.startswith("# "):
        return body
    return f"# {title}\n\n{body}"


def _normalize_list_indent(body: str) -> str:
    """统一列表缩进为2空格"""
    lines = body.split("\n")
    result = []
    for line in lines:
        match = re.match(r'^(\s*)([-*+]|\d+\.)\s', line)
        if match:
            indent = match.group(1)
            # 计算缩进级别（每4或tab算一级，输出为2空格/级）
            level = len(indent.replace('\t', '    ')) // 4
            new_indent = "  " * level
            line = new_indent + line.lstrip()
        result.append(line)
    return "\n".join(result)
