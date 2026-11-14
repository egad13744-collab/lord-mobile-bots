"""Ledger audit: hash chain, verifikasi, undo, dan backup.

Setiap entri `state/transactions.jsonl` diberi `id` berurutan, `prev_hash`, dan
`hash` (SHA-256 dari isi entri + prev_hash). Efeknya:

* Menghapus/me-edit satu baris di tengah membuat rantai putus → `verify_chain`
  melaporkan indeks yang rusak. Ini penting karena file audit bisa dibuka user.
* `undo` memakai entri terakhir untuk mengembalikan saldo, dengan mencatat
  transaksi pembalik (append-only: tidak ada baris yang dihapus).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

GENESIS = "0" * 64
_HASH_FIELDS = ("id", "ts", "kind", "nick", "rss", "note", "actor", "balance_before", "balance_after")


def entry_payload(record: Dict) -> str:
    """Representasi stabil isi entri (tanpa field hash)."""
    subset = {k: record.get(k) for k in _HASH_FIELDS}
    return json.dumps(subset, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_hash(record: Dict, prev_hash: str) -> str:
    return hashlib.sha256((prev_hash + entry_payload(record)).encode("utf-8")).hexdigest()


def read_entries(path: str | Path) -> List[Dict]:
    p = Path(path)
    if not p.exists():
        return []
    out: List[Dict] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"__corrupt__": line[:120]})
    return out


def verify_chain(path: str | Path) -> Tuple[bool, int, int]:
    """Kembalikan (utuh?, indeks_rusak, jumlah_entri_terbaca)."""
    entries = read_entries(path)
    prev = GENESIS
    for idx, rec in enumerate(entries):
        if "__corrupt__" in rec:
            return False, idx, len(entries)
        stored = rec.get("hash")
        if stored is None:  # histori lama tidak dapat dinyatakan utuh tanpa hash
            return False, idx, len(entries)
        if rec.get("prev_hash") != prev:
            return False, idx, len(entries)
        if compute_hash(rec, prev) != stored:
            return False, idx, len(entries)
        prev = stored
    return True, -1, len(entries)


def last_hash(path: str | Path) -> str:
    entries = read_entries(path)
    for rec in reversed(entries):
        if rec.get("hash"):
            return str(rec["hash"])
    return GENESIS


def next_id(path: str | Path) -> int:
    entries = read_entries(path)
    for rec in reversed(entries):
        if isinstance(rec.get("id"), int):
            return int(rec["id"]) + 1
    return len([e for e in entries if "__corrupt__" not in e]) + 1


def find_entry(path: str | Path, tx_id: int) -> Optional[Dict]:
    for rec in read_entries(path):
        if rec.get("id") == tx_id:
            return rec
    return None


def last_mutable_entry(path: str | Path, kinds: Iterable[str]) -> Optional[Dict]:
    allowed = set(kinds)
    entries = read_entries(path)
    undone = set()
    for rec in entries:
        if rec.get("kind") == "undo":
            import re
            match = re.search(r"undo #([0-9]+)", str(rec.get("note", "")))
            if match:
                undone.add(int(match.group(1)))
    for rec in reversed(entries):
        if rec.get("kind") in allowed and rec.get("balance_before") is not None:
            if int(rec.get("id", -1)) in undone:
                continue
            return rec
    return None


# --------------------------------------------------------------------------- #
# Backup rotasi
# --------------------------------------------------------------------------- #
def backup_file(src: str | Path, dest_dir: str | Path, keep: int = 7) -> Optional[Path]:
    """Salin file state ke dest_dir dengan nama bertimestamp; simpan `keep` terakhir."""
    s = Path(src)
    if not s.exists():
        return None
    d = Path(dest_dir)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1_000_000_000:09d}"
    out = d / f"{s.stem}-{stamp}{s.suffix}"
    out.write_bytes(s.read_bytes())
    backups = sorted(d.glob(f"{s.stem}-*{s.suffix}"))
    for old in backups[:-keep] if keep > 0 else []:
        try:
            old.unlink()
        except OSError:  # pragma: no cover
            pass
    return out


def list_backups(src: str | Path, dest_dir: str | Path) -> List[Path]:
    s = Path(src)
    d = Path(dest_dir)
    if not d.exists():
        return []
    return sorted(d.glob(f"{s.stem}-*{s.suffix}"))
