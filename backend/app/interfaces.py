"""
interfaces.py - 三道接缝接口定义
Phase 1 地基加固：本轮只定义接口 + 本地实现，平台版留扩展点。

三道接缝：
  1. 身份接缝（Identity Seam）：桌面版 = 本地单用户
  2. 存储接缝（Storage Seam）：本地文件系统实现，未来可替换为云存储
  3. 检索接缝（Retrieval Seam）：当前 SQLite ilike，Phase 6 升级为 FTS5
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================
# 接缝一：身份接缝
# ============================================================

def get_current_principal() -> dict:
    """
    桌面版 = 本地单用户，返回固定身份。
    平台版将替换为从 JWT / Session 中提取用户信息。
    """
    return {
        "user_id": "local_user",
        "username": "本地用户",
        "role": "admin",
        "is_local": True,
    }


# ============================================================
# 接缝二：存储接缝
# ============================================================

class StorageBackend(ABC):
    """抽象存储后端接口"""

    @abstractmethod
    def read(self, path: str) -> bytes:
        """读取文件内容"""
        ...

    @abstractmethod
    def write(self, path: str, data: bytes) -> None:
        """写入文件内容"""
        ...

    @abstractmethod
    def list(self, prefix: str) -> List[str]:
        """列出指定前缀下的所有文件路径"""
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        ...

    @abstractmethod
    def delete(self, path: str) -> None:
        """删除文件"""
        ...


class LocalStorageBackend(StorageBackend):
    """本地文件系统实现"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def read(self, path: str) -> bytes:
        return (self.base_dir / path).read_bytes()

    def write(self, path: str, data: bytes) -> None:
        target = self.base_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def list(self, prefix: str) -> List[str]:
        base = self.base_dir / prefix
        if not base.exists():
            return []
        return [
            str(p.relative_to(self.base_dir))
            for p in base.rglob("*")
            if p.is_file()
        ]

    def exists(self, path: str) -> bool:
        return (self.base_dir / path).exists()

    def delete(self, path: str) -> None:
        target = self.base_dir / path
        if target.exists():
            target.unlink()


# ============================================================
# 接缝三：检索接缝
# ============================================================

class RetrievalEngine(ABC):
    """抽象检索引擎接口"""

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        检索相关片段。

        返回：[{chunk_id, content, score, metadata}, ...]
        """
        ...

    @abstractmethod
    def index(self, chunks: List[Dict[str, Any]]) -> int:
        """
        索引若干 chunk。

        返回：成功索引数量
        """
        ...


class SqliteRetrievalEngine(RetrievalEngine):
    """
    Phase 6 已升级为 FTS5：实际实现见 app.retrieval.FTS5RetrievalEngine。
    此类保留为兼容入口，内部委托给 FTS5RetrievalEngine。
    """

    def __init__(self, engine):
        self._engine = engine
        self._engine_impl = None

    def _get_engine(self):
        if self._engine_impl is None:
            # 延迟导入避免循环依赖
            from app.retrieval import FTS5RetrievalEngine

            self._engine_impl = FTS5RetrievalEngine(self._engine)
        return self._engine_impl

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return self._get_engine().search(query, top_k, filters)

    def index(self, chunks: List[Dict[str, Any]]) -> int:
        return self._get_engine().index(chunks)
