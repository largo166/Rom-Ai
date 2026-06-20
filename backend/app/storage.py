from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.safety import validate_path


class StorageBackend(ABC):
    @abstractmethod
    def read(self, path: str | Path) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def write(self, path: str | Path, data: bytes) -> Path:
        raise NotImplementedError

    @abstractmethod
    def list(self, path: str | Path) -> list[Path]:
        raise NotImplementedError

    @abstractmethod
    def exists(self, path: str | Path) -> bool:
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    def read(self, path: str | Path) -> bytes:
        return validate_path(path, must_exist=True).read_bytes()

    def write(self, path: str | Path, data: bytes) -> Path:
        target = validate_path(path, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def list(self, path: str | Path) -> list[Path]:
        root = validate_path(path, must_exist=True, must_be_dir=True)
        return list(root.iterdir())

    def exists(self, path: str | Path) -> bool:
        try:
            return validate_path(path, must_exist=False).exists()
        except ValueError:
            return False
