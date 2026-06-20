"""
收件箱一键归档引擎
流程：分层扫描 → 出方案 → dry-run → 确认执行 → manifest → 入库
"""
import os
import json
import hashlib
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class ArchiveItem:
    """单个归档项"""
    source_path: str
    target_path: str
    file_type: str  # 文件类型标识
    category: str  # 分类：project_doc/meeting/knowledge/design_process/other
    confidence: float  # 置信度 0-1
    reason: str  # 匹配理由
    file_size: int = 0
    file_hash: str = ""
    status: str = "pending"  # pending/done/skipped/error/conflict/ready
    is_duplicate: bool = False
    duplicate_of: str = ""


@dataclass
class ArchivePlan:
    """完整归档方案"""
    plan_id: str
    source_folder: str
    target_base: str
    items: List[ArchiveItem] = field(default_factory=list)
    naming_template: str = "{city}-{project}-{stage}-{doc_type}-{version}-{date}"
    created_at: str = ""
    status: str = "draft"  # draft/confirmed/executing/done/rolled_back
    total_files: int = 0
    skipped_files: int = 0


@dataclass
class ArchiveManifest:
    """操作清单（用于撤销）"""
    manifest_id: str
    plan_id: str
    operations: List[Dict[str, str]] = field(default_factory=list)  # [{action, source, target, timestamp}]
    created_at: str = ""
    can_undo: bool = True


class ArchiveEngine:
    """归档引擎"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.manifests_dir = data_dir / "archive_manifests"
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def scan_folder(self, folder_path: Path) -> List[Dict[str, Any]]:
        """
        分层扫描：规则（文件名/类型/大小/时间）
        返回文件基本信息列表，不解析内容
        """
        results = []
        supported_ext = {'.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls',
                        '.txt', '.md', '.dwg', '.dxf', '.jpg', '.jpeg', '.png',
                        '.tif', '.tiff', '.bmp', '.zip', '.rar', '.7z'}

        for root, dirs, files in os.walk(folder_path):
            # 跳过隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in files:
                if fname.startswith('.'):
                    continue
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                try:
                    stat = fpath.stat()
                    results.append({
                        "path": str(fpath),
                        "name": fname,
                        "ext": ext,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "is_supported": ext in supported_ext,
                        "relative_path": str(fpath.relative_to(folder_path))
                    })
                except OSError as e:
                    logger.warning(f"无法读取文件信息: {fpath}: {e}")
        return results

    def compute_file_hash(self, file_path: Path) -> str:
        """计算文件哈希（用于重复检测）"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def detect_duplicates(self, items: List[ArchiveItem]) -> List[ArchiveItem]:
        """检测重复文件（相同大小+相同哈希）"""
        hash_map: Dict[str, ArchiveItem] = {}
        for item in items:
            key = f"{item.file_size}_{item.file_hash}"
            if key in hash_map and item.file_hash:
                item.is_duplicate = True
                item.duplicate_of = hash_map[key].source_path
            else:
                hash_map[key] = item
        return items

    def generate_plan(
        self,
        source_folder: str,
        target_base: str,
        scanned_files: List[Dict[str, Any]],
        classifications: List[Dict[str, Any]],
        naming_template: str = "{city}-{project}-{stage}-{doc_type}-{version}-{date}"
    ) -> ArchivePlan:
        """
        生成归档方案（dry-run 模式，不动文件）
        classifications 来自 AI 分类或规则匹配
        """
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        plan = ArchivePlan(
            plan_id=plan_id,
            source_folder=source_folder,
            target_base=target_base,
            naming_template=naming_template,
            created_at=datetime.now().isoformat(),
            total_files=len(scanned_files)
        )

        for scan_item, cls_item in zip(scanned_files, classifications):
            source = scan_item["path"]
            target_name = cls_item.get("suggested_name", scan_item["name"])
            target_subdir = cls_item.get("target_subdir", "未分类")

            archive_item = ArchiveItem(
                source_path=source,
                target_path=str(Path(target_base) / target_subdir / target_name),
                file_type=cls_item.get("file_type", "unknown"),
                category=cls_item.get("category", "other"),
                confidence=cls_item.get("confidence", 0.5),
                reason=cls_item.get("reason", ""),
                file_size=scan_item.get("size", 0),
                file_hash=self.compute_file_hash(Path(source)) if Path(source).exists() else ""
            )
            plan.items.append(archive_item)

        # 检测重复
        plan.items = self.detect_duplicates(plan.items)
        plan.skipped_files = sum(1 for item in plan.items if item.is_duplicate)

        return plan

    def execute_plan(self, plan: ArchivePlan, dry_run: bool = True) -> ArchiveManifest:
        """
        执行归档方案
        dry_run=True 只验证不执行
        默认复制到新结构，原文件不动
        """
        manifest = ArchiveManifest(
            manifest_id=f"manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            plan_id=plan.plan_id,
            created_at=datetime.now().isoformat()
        )

        if dry_run:
            # 只验证路径合法性和目标不冲突
            for item in plan.items:
                if item.is_duplicate and item.status != "force":
                    item.status = "skipped"
                    continue
                target = Path(item.target_path)
                if target.exists():
                    # 重名不静默覆盖
                    item.status = "conflict"
                    item.reason += f" [冲突：目标已存在]"
                else:
                    item.status = "ready"
            return manifest

        # 真实执行：复制文件
        plan.status = "executing"
        for item in plan.items:
            if item.status in ("skipped", "conflict"):
                continue
            try:
                target = Path(item.target_path)
                target.parent.mkdir(parents=True, exist_ok=True)

                if target.exists():
                    # 再次检查，绝不覆盖
                    item.status = "conflict"
                    continue

                shutil.copy2(item.source_path, str(target))
                item.status = "done"
                manifest.operations.append({
                    "action": "copy",
                    "source": item.source_path,
                    "target": str(target),
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                item.status = "error"
                logger.error(f"Archive copy failed: {item.source_path} → {item.target_path}: {e}")

        plan.status = "done"
        # 保存 manifest
        self._save_manifest(manifest)
        return manifest

    def undo_archive(self, manifest_id: str) -> Dict[str, Any]:
        """撤销归档操作（删除复制的文件）"""
        manifest_path = self.manifests_dir / f"{manifest_id}.json"
        if not manifest_path.exists():
            return {"success": False, "error": "Manifest not found"}

        manifest_data = json.loads(manifest_path.read_text(encoding='utf-8'))
        undone = 0
        errors = []

        for op in reversed(manifest_data.get("operations", [])):
            if op["action"] == "copy":
                target = Path(op["target"])
                if target.exists():
                    try:
                        target.unlink()
                        undone += 1
                        # 清理空目录
                        parent = target.parent
                        if parent.exists() and not any(parent.iterdir()):
                            parent.rmdir()
                    except Exception as e:
                        errors.append(f"Failed to remove {target}: {e}")

        return {"success": len(errors) == 0, "undone": undone, "errors": errors}

    def _save_manifest(self, manifest: ArchiveManifest):
        """保存操作清单"""
        path = self.manifests_dir / f"{manifest.manifest_id}.json"
        path.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding='utf-8')

    def get_manifest(self, manifest_id: str) -> Optional[Dict]:
        """读取操作清单"""
        path = self.manifests_dir / f"{manifest_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        return None

    def classify_by_rules(self, scanned_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        规则层分类（不依赖AI）：
        根据文件名、扩展名、大小、时间等规则进行初步分类
        """
        classifications = []

        # 文件类型关键词映射
        type_patterns = {
            "任务书": ["任务书", "设计任务", "briefing", "brief"],
            "会议纪要": ["会议", "纪要", "meeting", "minutes", "记录"],
            "方案": ["方案", "设计", "scheme", "design", "概念"],
            "汇报": ["汇报", "报告", "report", "presentation", "演示"],
            "图纸": ["总图", "平面", "立面", "剖面", "详图"],
            "技术": ["规范", "标准", "技术", "spec", "technical"],
            "合同": ["合同", "协议", "contract", "agreement"],
            "案例": ["案例", "参考", "reference", "case"],
        }

        ext_category = {
            '.pdf': 'document', '.docx': 'document', '.doc': 'document',
            '.pptx': 'presentation', '.ppt': 'presentation',
            '.xlsx': 'spreadsheet', '.xls': 'spreadsheet',
            '.dwg': 'drawing', '.dxf': 'drawing',
            '.jpg': 'image', '.jpeg': 'image', '.png': 'image',
            '.tif': 'image', '.tiff': 'image',
            '.zip': 'archive', '.rar': 'archive', '.7z': 'archive',
        }

        for file_info in scanned_files:
            name_lower = file_info["name"].lower()
            ext = file_info["ext"].lower()

            # 规则匹配
            matched_type = "other"
            confidence = 0.3
            reason = "仅根据扩展名分类"

            for ftype, keywords in type_patterns.items():
                if any(kw in name_lower for kw in keywords):
                    matched_type = ftype
                    confidence = 0.8
                    matched_keyword = next(kw for kw in keywords if kw in name_lower)
                    reason = f"文件名包含关键词'{matched_keyword}'"
                    break

            # 分类到目标子目录
            category_map = {
                "任务书": ("project_doc", "01-任务书"),
                "会议纪要": ("meeting", "02-会议"),
                "方案": ("project_doc", "03-方案"),
                "汇报": ("project_doc", "04-汇报"),
                "图纸": ("design_process", "05-图纸"),
                "技术": ("knowledge", "06-技术资料"),
                "合同": ("project_doc", "07-合同"),
                "案例": ("knowledge", "08-案例"),
                "other": ("other", "09-其他"),
            }

            cat, subdir = category_map.get(matched_type, ("other", "09-其他"))

            classifications.append({
                "file_type": matched_type,
                "category": cat,
                "target_subdir": subdir,
                "suggested_name": file_info["name"],  # 保留原名，AI可改
                "confidence": confidence,
                "reason": reason,
                "needs_ai": confidence < 0.6  # 低置信度标记需要AI处理
            })

        return classifications
