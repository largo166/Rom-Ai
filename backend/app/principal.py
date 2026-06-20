from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    id: str = "local-user"
    name: str = "本机用户"
    role: str = "owner"


def get_current_principal() -> Principal:
    return Principal()
