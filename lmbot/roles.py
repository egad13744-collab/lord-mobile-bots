"""Pangkat (rank), whitelist/blacklist, dan otorisasi pengirim perintah."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from .utils import find_nick, normalize_nick

RANK_ORDER: List[str] = ["R1", "R2", "R3", "R4", "R5", "R6"]
RANK_LABEL = {
    "R1": "R1 Member",
    "R2": "R2 Member",
    "R3": "R3 Member",
    "R4": "R4 Officer",
    "R5": "R5 Leader",
    "R6": "R6 Admin/Bot",
}


class PermissionError_(Exception):
    """Pengirim tidak berhak menjalankan perintah."""


def rank_level(rank: str) -> int:
    r = (rank or "R1").strip().upper()
    if r.isdigit():
        r = f"R{r}"
    return RANK_ORDER.index(r) if r in RANK_ORDER else 0


def rank_at_least(have: str, need: str) -> bool:
    return rank_level(have) >= rank_level(need)


@dataclass
class Roster:
    """Daftar izin. Sumber kebenaran: state/bank.json (persisten)."""

    owners: Set[str] = field(default_factory=set)
    whitelist: Dict[str, str] = field(default_factory=dict)   # nick -> rank
    blacklist: Set[str] = field(default_factory=set)
    known_members: Set[str] = field(default_factory=set)
    enforce_whitelist: bool = True
    default_rank: str = "R1"
    owner_rank: str = "R6"

    # -- mutasi -- #
    def add_owner(self, nick: str) -> None:
        self.owners.add(normalize_nick(nick))

    def set_member(self, nick: str, rank: str) -> None:
        rank = rank.upper()
        if rank not in RANK_ORDER:
            raise ValueError(f"rank tidak valid: {rank} (pakai R1-R5)")
        self.whitelist[normalize_nick(nick)] = rank
        self.known_members.add(normalize_nick(nick))
        self.blacklist.discard(normalize_nick(nick))

    def remove_member(self, nick: str) -> bool:
        key = normalize_nick(nick)
        existed = self.whitelist.pop(key, None) is not None
        return existed

    def blacklist_add(self, nick: str) -> None:
        key = normalize_nick(nick)
        self.blacklist.add(key)
        self.whitelist.pop(key, None)

    def blacklist_remove(self, nick: str) -> bool:
        key = normalize_nick(nick)
        existed = key in self.blacklist
        self.blacklist.discard(key)
        return existed

    # -- query -- #
    def is_blacklisted(self, nick: str) -> bool:
        return normalize_nick(nick) in self.blacklist

    def rank_of(self, nick: str) -> Optional[str]:
        key = normalize_nick(nick)
        if key in self.owners:
            return self.owner_rank
        if key in self.whitelist:
            return self.whitelist[key]
        if not self.enforce_whitelist:
            return self.default_rank
        return None

    def authorize(self, nick: str, required: str) -> str:
        """Kembalikan rank pengirim atau lempar PermissionError_."""
        if self.is_blacklisted(nick):
            raise PermissionError_(f"{nick} ada di blacklist")
        rank = self.rank_of(nick)
        if rank is None:
            raise PermissionError_(f"{nick} belum terdaftar di whitelist")
        if not rank_at_least(rank, required):
            raise PermissionError_(
                f"{nick} ({rank}) butuh minimal {required}"
            )
        return rank

    # -- serialisasi -- #
    def to_dict(self) -> dict:
        return {
            "owners": sorted(self.owners),
            "whitelist": dict(sorted(self.whitelist.items())),
            "blacklist": sorted(self.blacklist),
            "known_members": sorted(self.known_members),
            "enforce_whitelist": self.enforce_whitelist,
            "default_rank": self.default_rank,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "Roster":
        data = data or {}
        roster = cls(
            enforce_whitelist=bool(data.get("enforce_whitelist", True)),
            default_rank=data.get("default_rank", "R1"),
        )
        for owner in data.get("owners", []):
            roster.add_owner(owner)
        for nick, rank in (data.get("whitelist") or {}).items():
            try:
                roster.set_member(nick, rank)
            except ValueError:
                continue
        for nick in data.get("blacklist", []):
            roster.blacklist_add(nick)
        for nick in data.get("known_members", []):
            roster.known_members.add(normalize_nick(nick))
        return roster

    def resolve(self, nick: str) -> Optional[str]:
        """Cocokkan nick ketikan user dengan nick terdaftar."""
        pool: Iterable[str] = list(self.whitelist) + list(self.owners) + list(self.known_members)
        return find_nick(nick, pool)
