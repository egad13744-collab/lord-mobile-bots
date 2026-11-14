"""Penyimpanan state bank: saldo member, whitelist, log transaksi.

File JSON ditulis atomik (tmp + os.replace) agar tidak korup saat RDP putus
atau bot dimatikan paksa. Selain itu setiap perubahan dicatat ke audit log
append-only (JSON Lines) supaya bisa diaudit anggota klan.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import ledger
from .config import Config
from .roles import Roster
from .utils import normalize_nick

RSS_KEYS = ("food", "stone", "wood", "ore", "gold")
CODE_TO_KEY = {"F": "food", "S": "stone", "W": "wood", "O": "ore", "G": "gold"}
KEY_TO_CODE = {v: k for k, v in CODE_TO_KEY.items()}


@dataclass
class TxRecord:
    ts: float
    kind: str
    nick: str
    rss: Dict[str, int]
    note: str = ""
    actor: str = ""
    balance_after: Optional[Dict[str, int]] = None
    balance_before: Optional[Dict[str, int]] = None
    id: int = 0
    prev_hash: str = ""
    hash: str = ""

    def core(self) -> dict:
        """Isi yang ikut di-hash (tanpa id/prev_hash/hash/waktu string)."""
        return {
            "ts": round(float(self.ts), 3),
            "kind": self.kind,
            "nick": self.nick,
            "rss": self.rss,
            "note": self.note,
            "actor": self.actor,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts,
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts)),
            "kind": self.kind,
            "nick": self.nick,
            "rss": self.rss,
            "note": self.note,
            "actor": self.actor,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


class InsufficientFunds(Exception):
    pass


class BankStore:
    def __init__(self, cfg: Config, path: Optional[str] = None):
        self.cfg = cfg
        self.path = Path(path) if path else cfg.resolve_path(cfg.get("bank.path", "state/bank.json"))
        self.log_path = self.path.parent / "transactions.jsonl"
        self._lock = threading.RLock()
        self.roster = Roster()
        self.balances: Dict[str, Dict[str, int]] = {}
        self.frozen_until: float = 0.0
        self.created_at: float = time.time()
        self.meta: Dict[str, object] = {}
        self.dry_run: bool = bool(cfg.get("bot.dry_run", False))
        self.load()

    # ---------------------------------------------------------------- #
    # persist
    # ---------------------------------------------------------------- #
    def load(self) -> None:
        if not self.path.exists():
            self.roster = Roster(enforce_whitelist=bool(self.cfg.get("safety.whitelist_enforced", True)))
            for nick in self.cfg.get("bot.allowed_senders", []) or []:
                self.roster.set_member(nick, "R5")
            for nick in self.cfg.get("bot.owners", []) or []:
                self.roster.add_owner(nick)
            self.save()
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.roster = Roster.from_dict(data.get("roster"))
        if not self.roster.enforce_whitelist and self.cfg.get("safety.whitelist_enforced", True):
            self.roster.enforce_whitelist = True
        self.balances = {
            normalize_nick(nick): {k: int(v.get(k, 0)) for k in RSS_KEYS}
            for nick, v in (data.get("balances") or {}).items()
        }
        self.frozen_until = float(data.get("frozen_until") or 0)
        self.created_at = float(data.get("created_at") or time.time())
        self.meta = data.get("meta") or {}

    def save(self) -> None:
        if getattr(self, "dry_run", False):
            return
        with self._lock:
            payload = {
                "schema": 1,
                "created_at": self.created_at,
                "updated_at": time.time(),
                "frozen_until": self.frozen_until,
                "roster": self.roster.to_dict(),
                "balances": self.balances,
                "meta": self.meta,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)

    # ---------------------------------------------------------------- #
    # saldo
    # ---------------------------------------------------------------- #
    def _bucket(self, nick: str) -> Dict[str, int]:
        key = normalize_nick(nick)
        return self.balances.setdefault(key, {k: 0 for k in RSS_KEYS})

    def balance(self, nick: str) -> Dict[str, int]:
        key = normalize_nick(nick)
        return dict(self.balances.get(key) or {k: 0 for k in RSS_KEYS})

    def bank_total(self) -> Dict[str, int]:
        total = {k: 0 for k in RSS_KEYS}
        for bal in self.balances.values():
            for k in RSS_KEYS:
                total[k] += int(bal.get(k, 0))
        return total

    def member_count(self) -> int:
        return len(self.balances)

    def credit(self, nick: str, rss: Dict[str, int], note: str = "", actor: str = "") -> Dict[str, int]:
        if self.dry_run:
            return self.balance(nick)
        with self._lock:
            bal = self._bucket(nick)
            before = dict(bal)
            for k, v in rss.items():
                if v < 0:
                    raise ValueError("rss negatif")
                bal[k] = int(bal.get(k, 0)) + int(v)
            self._audit(TxRecord(time.time(), "credit", nick, dict(rss), note, actor,
                                 dict(bal), before))
            if self.cfg.get("bank.save_every_command", True):
                self.save()
            return dict(bal)

    def debit(
        self,
        nick: str,
        rss: Dict[str, int],
        note: str = "",
        actor: str = "",
        allow_negative: bool = False,
    ) -> Dict[str, int]:
        if self.dry_run:
            return self.balance(nick)
        with self._lock:
            bal = self._bucket(nick)
            for k, v in rss.items():
                if not allow_negative and bal.get(k, 0) < int(v):
                    short = int(v) - int(bal.get(k, 0))
                    raise InsufficientFunds(
                        f"saldo {k} {nick} kurang {short:,} (punya {bal.get(k, 0):,})"
                    )
            before = dict(bal)
            for k, v in rss.items():
                bal[k] = int(bal.get(k, 0)) - int(v)
            self._audit(TxRecord(time.time(), "debit", nick, dict(rss), note, actor,
                                 dict(bal), before))
            if self.cfg.get("bank.save_every_command", True):
                self.save()
            return dict(bal)

    def set_balance(self, nick: str, rss: Dict[str, int], actor: str = "") -> Dict[str, int]:
        if self.dry_run:
            return dict(rss)
        with self._lock:
            key = normalize_nick(nick)
            before = self.balance(key)
            self.balances[key] = {k: int(rss.get(k, 0)) for k in RSS_KEYS}
            delta = {k: self.balances[key][k] - before.get(k, 0) for k in RSS_KEYS}
            self._audit(TxRecord(time.time(), "set", nick, delta, "set manual", actor,
                                 dict(self.balances[key]), before))
            self.save()
            return dict(self.balances[key])

    def _audit(self, rec: TxRecord) -> None:
        """Tulis entri audit dengan hash chain (deteksi manipulasi manual)."""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            prev = ledger.last_hash(self.log_path)
            rec.id = ledger.next_id(self.log_path)
            rec.prev_hash = prev
            # hash dihitung dari versi yang dipakai `verify_chain`
            payload = {
                "id": rec.id, "ts": rec.ts, "kind": rec.kind, "nick": rec.nick, "rss": rec.rss,
                "note": rec.note, "actor": rec.actor,
                "balance_before": rec.balance_before, "balance_after": rec.balance_after,
            }
            rec.hash = ledger.compute_hash(payload, prev)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ---------------------------------------------------------------- #
    # status bank
    # ---------------------------------------------------------------- #
    def freeze(self, seconds: int, actor: str = "") -> float:
        self.frozen_until = time.time() + max(0, seconds)
        self._audit(TxRecord(time.time(), "freeze", "-", {}, f"{seconds}s", actor))
        self.save()
        return self.frozen_until

    def unfreeze(self, actor: str = "") -> None:
        self.frozen_until = 0.0
        self._audit(TxRecord(time.time(), "unfreeze", "-", {}, "", actor))
        self.save()

    def is_frozen(self) -> bool:
        return time.time() < self.frozen_until

    def freeze_remaining(self) -> int:
        return max(0, int(self.frozen_until - time.time()))

    # ---------------------------------------------------------------- #
    # ringkasan
    # ---------------------------------------------------------------- #
    def leaderboard(self, key: str = "food", limit: int = 10) -> List[tuple]:
        rows = [(nick, int(bal.get(key, 0))) for nick, bal in self.balances.items()]
        rows.sort(key=lambda r: r[1], reverse=True)
        return rows[:limit]

    def stats(self) -> dict:
        total = self.bank_total()
        return {
            "members": self.member_count(),
            "total": total,
            "whitelist": len(self.roster.whitelist),
            "blacklist": len(self.roster.blacklist),
            "frozen_until": self.frozen_until,
            "transactions": self.count_transactions(),
        }

    # ---------------------------------------------------------------- #
    # integritas & undo
    # ---------------------------------------------------------------- #
    def verify_audit(self):
        """(utuh, indeks_rusak, jumlah_entri)."""
        with self._lock:
            return ledger.verify_chain(self.log_path)

    def backup(self, keep: int = 7):
        """Salin bank.json + audit ke state/backups/ (rotasi `keep`)."""
        dest = self.path.parent / "backups"
        out = []
        with self._lock:
            for src in (self.path, self.log_path):
                res = ledger.backup_file(src, dest, keep=keep)
                if res:
                    out.append(res)
        return out

    def undo_last(self, actor: str = "", kinds=("credit", "debit")):
        """Batalkan transaksi terakhir; kembalikan (entri, saldo_baru) atau (None, None).

        Pembatalan ditulis sebagai entri baru (`kind: undo`) — audit tetap
        append-only, tidak ada baris yang dihapus.
        """
        with self._lock:
            # Verifikasi + cari kandidat + ubah saldo atomik terhadap mutasi lain.
            if not self.verify_audit()[0]:
                return None, None
            entry = ledger.last_mutable_entry(self.log_path, kinds)
            if not entry:
                return None, None
            # Undo ledger-only adjustments. A transfer/RSS action has already
            # affected the game and cannot safely be reversed by editing balances.
            note = str(entry.get("note") or "").lower()
            if any(marker in note for marker in ("transfer", "donate", "adminrss", "rss", "refund", "setbal")):
                return None, None
            nick = str(entry.get("nick") or "")
            before = entry.get("balance_before") or {}
            if not nick or not isinstance(before, dict):
                return None, None
            key = normalize_nick(nick)
            current = self.balance(key)
            self.balances[key] = {k: int(before.get(k, 0) or 0) for k in RSS_KEYS}
            delta = {k: self.balances[key][k] - current.get(k, 0) for k in RSS_KEYS}
            self._audit(TxRecord(time.time(), "undo", nick, delta,
                                 f"undo #{entry.get('id')} ({entry.get('kind')})",
                                 actor, dict(self.balances[key]), current))
            self.save()
            return entry, dict(self.balances[key])

    # ---------------------------------------------------------------- #
    # kuota harian
    # ---------------------------------------------------------------- #
    def quota_used(self, nick: str, key: str, day: Optional[str] = None) -> int:
        """Jumlah RSS yang sudah dikirim hari ini (dari audit log)."""
        day = day or time.strftime("%Y-%m-%d")
        nkey = normalize_nick(nick)
        total = 0
        with self._lock:
            entries = ledger.read_entries(self.log_path)
        for rec in entries:
            if "__corrupt__" in rec:
                continue
            ts = float(rec.get("ts") or 0)
            if time.strftime("%Y-%m-%d", time.localtime(ts)) != day:
                continue
            if normalize_nick(str(rec.get("nick") or "")) != nkey:
                continue
            kind = str(rec.get("kind") or "")
            note = str(rec.get("note") or "").lower()
            amount = int((rec.get("rss") or {}).get(key, 0) or 0)
            send_markers = ("transfer", "donate", "adminrss", "rss")
            if kind == "debit" and any(marker in note for marker in send_markers):
                total += amount
            elif kind == "credit" and "refund" in note:
                total = max(0, total - amount)
        return total

    def count_transactions(self) -> int:
        if not self.log_path.exists():
            return 0
        with self.log_path.open("rb") as fh:
            return sum(1 for _ in fh)

    def recent(self, limit: int = 10) -> List[dict]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
