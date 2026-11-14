"""Alias & perintah custom dari `config/commands.yaml`.

Tujuan: admin klan bisa menambah nama pendek (`!b` -> `!bal`) atau perintah
teks statis (`!aturan`) tanpa menyentuh kode. Semua opsional — bila file tidak
ada, bot berjalan seperti biasa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml


@dataclass
class CustomCommand:
    name: str
    reply: str
    min_rank: str = "R1"
    description: str = ""


@dataclass
class CustomSet:
    aliases: Dict[str, str] = field(default_factory=dict)
    custom: Dict[str, CustomCommand] = field(default_factory=dict)
    source: Optional[Path] = None

    @property
    def loaded(self) -> bool:
        return bool(self.aliases or self.custom)

    def resolve_alias(self, text: str) -> str:
        """Ganti token pertama bila alias dikenal: 'b 1m' -> 'bal 1m'."""
        body = (text or "").strip()
        if not body:
            return text
        prefix = ""
        if body[:1] in "!/.":
            prefix, body = body[0], body[1:]
        head, _, rest = body.partition(" ")
        target = self.aliases.get(head.lower())
        if not target:
            return text
        return f"{prefix}{target}" + (f" {rest}" if rest else "")

    def lookup(self, name: str) -> Optional[CustomCommand]:
        return self.custom.get((name or "").lower())


def load_custom(path: str | Path | None) -> CustomSet:
    out = CustomSet()
    if not path:
        return out
    p = Path(path)
    if not p.exists():
        return out
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return out
    out.source = p
    for key, target in (data.get("aliases") or {}).items():
        if isinstance(key, str) and isinstance(target, str):
            out.aliases[key.lower()] = target.strip().lstrip("!/")
    for key, meta in (data.get("custom") or {}).items():
        if not isinstance(meta, dict):
            continue
        reply = str(meta.get("reply") or "").strip()
        if not key or not reply:
            continue
        out.custom[str(key).lower()] = CustomCommand(
            name=str(key).lower(),
            reply=reply,
            min_rank=str(meta.get("min_rank", "R1")).upper(),
            description=str(meta.get("description", "") or ""),
        )
    return out
