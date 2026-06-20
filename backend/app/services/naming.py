"""统一命名模板引擎"""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

NAMING_TEMPLATE = "{project}-{type}-{date}-{seq:03d}"


def generate_standard_name(
    project: str,
    file_type: str,
    date: Optional[str] = None,
    seq: int = 1,
    ext: str = "",
) -> str:
    """生成标准文件名: 项目名-类型-日期-序号.ext"""
    safe_project = _sanitize(project)
    safe_type = _sanitize(file_type)
    if not date:
        date = datetime.now().strftime("%Y%m%d")
    name = NAMING_TEMPLATE.format(project=safe_project, type=safe_type, date=date, seq=seq)
    if ext:
        ext = ext if ext.startswith(".") else f".{ext}"
        name += ext
    return name


def batch_rename_plan(
    files: list,  # [{"id": str, "filename": str, "project": str, "type": str, "date": str}]
    project_default: str = "",
) -> list:
    """批量生成重命名方案，自动处理序号和冲突"""
    # 按 project+type+date 分组计数
    counters: dict = {}
    plan = []
    for f in files:
        proj = f.get("project") or project_default or "未分类"
        ftype = f.get("type") or "文档"
        date = f.get("date") or datetime.now().strftime("%Y%m%d")
        key = f"{proj}-{ftype}-{date}"
        counters[key] = counters.get(key, 0) + 1
        ext = Path(f["filename"]).suffix
        new_name = generate_standard_name(proj, ftype, date, counters[key], ext)
        plan.append({
            "id": f.get("id", ""),
            "original": f["filename"],
            "new_name": new_name,
            "project": proj,
            "type": ftype,
        })
    return plan


def detect_naming_conflicts(plan: list) -> list:
    """检测重命名方案中的冲突"""
    seen: dict = {}
    conflicts = []
    for item in plan:
        name = item["new_name"]
        if name in seen:
            conflicts.append({"name": name, "items": [seen[name]["id"], item["id"]]})
        else:
            seen[name] = item
    return conflicts


def _sanitize(text: str) -> str:
    """清理文件名中的非法字符"""
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', '', text)
    text = re.sub(r'\s+', '_', text)
    return text[:30] if text else "未命名"
