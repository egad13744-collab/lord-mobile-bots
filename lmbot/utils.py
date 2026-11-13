"""Util umum: parsing angka, normalisasi nick, rate limit, waktu."""
from __future__ import annotations

import random
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

SUFFIXES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}

_AMOUNT_RE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([kmb])?\s*$", re.IGNORECASE)


class ParseError(Exception):
    """Input dari chat tidak bisa dipahami."""


def parse_amount(text: str, suffixes: Optional[dict] = None, allow_zero: bool = False) -> int:
    """'100m' -> 100000000, '1.5k' -> 1500, '250' -> 250.

    Koma diperlakukan sebagai pemisah ribuan gaya Indonesia bila diikuti
    tepat 3 digit ('1,000') dan sebagai desimal bila tidak ('1,5').
    """
    table = {k: (suffixes or {}).get(k, v) for k, v in SUFFIXES.items()}
    m = _AMOUNT_RE.match(text or "")
    if not m:
        raise ParseError(f"jumlah tidak valid: {text!r}")
    num, suf = m.group(1), (m.group(2) or "").lower()
    if "," in num and "." in num:
        num = num.replace(",", "")
    elif "," in num:
        head, _, tail = num.partition(",")
        num = head + tail if len(tail) == 3 else head + "." + tail
    value = float(num) * (table.get(suf, 1) if suf else 1)
    if value < 0 or (value == 0 and not allow_zero):
        raise ParseError("jumlah harus lebih dari 0")
    return int(round(value))


def normalize_nick(nick: str) -> str:
    """Samakan nick untuk pencocokan: huruf kecil, tanpa spasi/underscore."""
    s = unicodedata.normalize("NFKC", nick or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower().replace(" ", "").replace("_", "")


def nick_match(candidate: str, target: str) -> bool:
    return bool(target) and normalize_nick(candidate) == normalize_nick(target)


def find_nick(candidate: str, known: Iterable[str]) -> Optional[str]:
    """Cari nick yang paling mirip (exact dulu, lalu prefix tunggal)."""
    cand = normalize_nick(candidate)
    pool = list(known)
    for name in pool:
        if normalize_nick(name) == cand:
            return name
    near = [n for n in pool if normalize_nick(n).startswith(cand) or cand.startswith(normalize_nick(n))]
    return near[0] if len(near) == 1 else None


def parse_rss_vector(text: str, codes: str = "FSWOG", suffixes: Optional[dict] = None) -> dict:
    """'5m 5m 5m 5m 5m' atau '5m,3m,1m,0,0' -> {'F':5000000,...}."""
    raw = re.split(r"[\s,;]+", (text or "").strip())
    parts = [p for p in raw if p]
    if not parts:
        raise ParseError("daftar RSS kosong")
    if len(parts) > len(codes):
        raise ParseError(f"terlalu banyak komponen RSS (maks {len(codes)})")
    out = {}
    for code, part in zip(codes, parts):
        out[code] = parse_amount(part, suffixes, allow_zero=True)
    for code in codes[len(parts):]:
        out[code] = 0
    return out


def fmt_rss(amounts: dict, labels: Optional[dict] = None) -> str:
    labs = labels or {"F": "Food", "S": "Stone", "W": "Wood", "O": "Ore", "G": "Gold"}
    return " ".join(f"{labs.get(k, k)}:{human(v)}" for k, v in amounts.items())


def human(value: float) -> str:
    v = float(value)
    for unit, size in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if abs(v) >= size:
            txt = f"{v / size:.2f}".rstrip("0").rstrip(".")
            return f"{txt}{unit}"
    return str(int(v)) if v == int(v) else f"{v:.2f}"


def parse_duration(text: str) -> int:
    """'3600' -> detik; '1 (1 jam)' tidak didukung; '2h'/'30m'/'45s' didukung."""
    t = (text or "").strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([hms]?)", t)
    if not m:
        raise ParseError(f"durasi tidak valid: {text!r}")
    val = float(m.group(1))
    unit = m.group(2) or "s"
    factor = {"s": 1, "m": 60, "h": 3600}[unit]
    return int(val * factor)


@dataclass
class RateLimiter:
    """Batasi jumlah perintah yang dieksekusi per menit."""

    per_minute: int = 20
    _stamps: list = field(default_factory=list)

    def allow(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        self._stamps = [t for t in self._stamps if now - t < 60]
        if len(self._stamps) >= self.per_minute:
            return False
        self._stamps.append(now)
        return True

    def wait_time(self, now: Optional[float] = None) -> float:
        now = time.monotonic() if now is None else now
        self._stamps = [t for t in self._stamps if now - t < 60]
        if len(self._stamps) < self.per_minute:
            return 0.0
        return max(0.0, 60 - (now - self._stamps[0]))


def jitter_point(x: int, y: int, spread: int = 4) -> tuple[int, int]:
    """Geser titik sedikit agar tidak mencurigakan seperti macro kaku."""
    if spread <= 0:
        return x, y
    return x + random.randint(-spread, spread), y + random.randint(-spread, spread)


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
