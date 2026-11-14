"""OCR ringan tanpa API eksternal: pembaca digit berbasis template.

Bot premium membaca angka langsung dari layar (isi tas bank, jumlah kiriman).
Modul ini melakukan hal yang sama dengan pendekatan paling andal untuk UI game:
**template digit 0-9** di `assets/ocr/` + segmentasi kolom.

Alur:
    screenshot -> crop area angka -> binarisasi (Otsu) -> segmentasi kolom
    -> cocokkan tiap potongan dengan 10 template digit -> angka

Kenapa bukan Tesseract? Karena angka UI game memakai font yang konsisten;
template 10 digit jauh lebih akurat, cepat (<50 ms), dan tanpa instalasi
tambahan. Bila `assets/ocr/` belum ada, modul menyediakan `train_digits()` untuk
membuatnya dari satu screenshot yang sudah dipotong.

Semuanya offline: gambar tidak pernah dikirim ke mana pun.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .imaging import Image, ImageError, load_image

# Rasio aspek digit UI game umumnya 0.4-0.8; di luar itu dianggap noise.
MIN_GLYPH_W = 3
MIN_GLYPH_H = 8


@dataclass
class Glyph:
    x: int
    width: int
    pixels: bytes  # biner 0/255, ukuran height*width

    def as_image(self, height: int) -> Image:
        return Image(self.width, height, 1, self.pixels)


@dataclass
class TextBox:
    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]


def to_binary(img: Image, threshold: Optional[int] = None) -> Tuple[Image, int]:
    """Gray -> biner (0/255) dengan threshold Otsu sederhana."""
    gray = img.to_gray().data
    w, h = img.width, img.height
    if threshold is None:
        hist = [0] * 256
        for v in gray:
            hist[v] += 1
        total = w * h
        sum_all = sum(i * hist[i] for i in range(256))
        sum_b = 0.0
        w_b = 0
        best, best_var = 127, -1.0
        for t in range(256):
            w_b += hist[t]
            if w_b == 0:
                continue
            w_f = total - w_b
            if w_f == 0:
                break
            sum_b += t * hist[t]
            m_b = sum_b / w_b
            m_f = (sum_all - sum_b) / w_f
            var = w_b * w_f * (m_b - m_f) ** 2
            if var > best_var:
                best_var, best = var, t
        threshold = best
    out = bytes(255 if v > threshold else 0 for v in gray)
    return Image(w, h, 1, out), int(threshold)


def segment_columns(img: Image, min_gap: int = 2) -> List[Glyph]:
    """Potong gambar biner menjadi kolom berisi glyph (dipisah kolom kosong)."""
    w, h = img.width, img.height
    data = img.data
    ink = [False] * w
    for x in range(w):
        for y in range(h):
            if data[y * w + x] > 0:
                ink[x] = True
                break
    glyphs: List[Glyph] = []
    start = None
    gap = 0
    for x in range(w):
        if ink[x]:
            if start is None:
                start = x
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                glyphs.append(_cut(img, start, x - gap))
                start = None
                gap = 0
    if start is not None:
        glyphs.append(_cut(img, start, w - 1))
    return [g for g in glyphs if g.width >= MIN_GLYPH_W]


def _cut(img: Image, x0: int, x1: int) -> Glyph:
    x0 = max(0, min(x0, img.width - 1))
    x1 = max(x0, min(x1, img.width - 1))
    w = max(1, x1 - x0 + 1)
    h = img.height
    buf = bytearray(w * h)
    for y in range(h):
        row = y * img.width
        for i in range(w):
            buf[y * w + i] = img.data[row + x0 + i]
    return Glyph(x0, w, bytes(buf))


def _normalize(glyph: Glyph, size: int = 16) -> bytes:
    """Skala glyph ke kotak size x size (nearest neighbour) untuk perbandingan."""
    h = glyph_height(glyph)
    out = bytearray(size * size)
    for j in range(size):
        sy = min(h - 1, int(j * h / size))
        for i in range(size):
            sx = min(glyph.width - 1, int(i * glyph.width / size))
            out[j * size + i] = glyph.pixels[sy * glyph.width + sx]
    return bytes(out)


def glyph_height(glyph: Glyph) -> int:
    if glyph.width == 0:
        return 0
    return len(glyph.pixels) // glyph.width


class DigitOCRError(Exception):
    pass


class DigitOCR:
    """Pembaca digit memakai template `assets/ocr/<digit>.png`."""

    def __init__(self, template_dir: str | Path = "assets/ocr", size: int = 16):
        self.dir = Path(template_dir)
        self.size = size
        self.templates: Dict[str, bytes] = {}
        self.load()

    # -- template -- #
    def load(self) -> int:
        self.templates.clear()
        if not self.dir.exists():
            return 0
        for png in sorted(self.dir.glob("*.png")):
            key = png.stem.strip()
            if key not in "0123456789":
                continue
            try:
                img = load_image(png).to_gray()
            except (ImageError, OSError):
                continue
            binary, _ = to_binary(img)
            glyphs = segment_columns(binary)
            if not glyphs:
                continue
            self.templates[key] = _normalize(glyphs[0], self.size)
        return len(self.templates)

    @property
    def ready(self) -> bool:
        return len(self.templates) >= 8

    def missing_digits(self) -> List[str]:
        return [d for d in "0123456789" if d not in self.templates]

    # -- baca -- #
    def _match(self, glyph: Glyph) -> Tuple[str, float]:
        norm = _normalize(glyph, self.size)
        best, best_score = "?", -1.0
        for digit, tpl in self.templates.items():
            same = sum(1 for a, b in zip(norm, tpl) if (a > 0) == (b > 0))
            score = same / len(norm)
            if score > best_score:
                best, best_score = digit, score
        return best, max(0.0, best_score)

    def read_image(self, img: Image, min_score: float = 0.72) -> TextBox:
        if not self.ready:
            raise DigitOCRError(
                f"template digit belum lengkap di {self.dir} "
                f"(kurang: {', '.join(self.missing_digits())}). Jalankan "
                f"`code.py ocr train --screen <file> --box x,y,w,h`."
            )
        binary, _ = to_binary(img)
        glyphs = segment_columns(binary)
        if not glyphs:
            return TextBox("", 0.0, (0, 0, img.width, img.height))
        chars: List[str] = []
        scores: List[float] = []
        h = glyph_height(glyphs[0])
        for glyph in glyphs:
            digit, score = self._match(glyph)
            if score < min_score:
                chars.append("?")
            else:
                chars.append(digit)
            scores.append(score)
        text = "".join(chars)
        return TextBox(text, sum(scores) / len(scores), (0, 0, img.width, h))

    def read_file(self, path: str | Path, box: Optional[Sequence] = None,
                  min_score: float = 0.72) -> TextBox:
        img = load_image(path)
        if box:
            img = img.crop_fraction(box)
        return self.read_image(img, min_score=min_score)


def parse_number(text: str, suffixes: Optional[dict] = None) -> Optional[int]:
    """'12,3M' / '1.234.567' / '45K' -> int; None bila tidak ada angka."""
    suffixes = suffixes or {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    cleaned = (text or "").strip().lower().replace(" ", "")
    m = re.search(r"(\d[\d.,]*)([kmb]?)", cleaned)
    if not m:
        return None
    num, suf = m.group(1), m.group(2)
    if not any(ch.isdigit() for ch in num):
        return None
    if "," in num and "." in num:
        # Pemisah paling kanan adalah desimal hanya jika 1-2 digit sesudahnya.
        if num.rfind(",") > num.rfind("."):
            left, right = num.rsplit(",", 1)
            num = left.replace(".", "").replace(",", "") + ("." + right if len(right) <= 2 else right)
        else:
            left, right = num.rsplit(".", 1)
            num = left.replace(",", "").replace(".", "") + ("." + right if len(right) <= 2 else right)
    elif "," in num or "." in num:
        sep = "," if "," in num else "."
        parts = num.split(sep)
        if len(parts) > 2 or (len(parts[-1]) == 3 and not suf):
            num = "".join(parts)
        else:
            num = ".".join(parts)
    try:
        value = float(num)
    except ValueError:
        return None
    return int(value * suffixes.get(suf, 1))


# --------------------------------------------------------------------------- #
# Pelatihan template digit dari satu screenshot
# --------------------------------------------------------------------------- #
def train_digits(screen_path: str | Path, box: Sequence[float], out_dir: str | Path,
                 digits: str = "0123456789", save_preview: bool = True) -> Dict[str, Path]:
    """Potong `box` (berisi baris angka) lalu simpan tiap digit ke out_dir.

    Syarat: urutan glyph di box harus sama dengan `digits`
    (default '0123456789'). Praktis: ambil screenshot deret angka contoh
    seperti "0123456789" dari UI game, tandai kotaknya, jalankan sekali.
    """
    img = load_image(screen_path).crop_fraction(box)
    binary, _ = to_binary(img)
    glyphs = segment_columns(binary)
    if len(glyphs) < len(digits):
        raise DigitOCRError(
            f"hanya {len(glyphs)} glyph terdeteksi, butuh {len(digits)}. "
            f"Perbesar box atau pastikan hanya angka yang masuk kotak."
        )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved: Dict[str, Path] = {}
    h = glyph_height(glyphs[0])
    for digit, glyph in zip(digits, glyphs):
        img_glyph = Image(glyph.width, h, 1, glyph.pixels)
        path = img_glyph.save_png(out / f"{digit}.png", gray=True)
        saved[digit] = path
        if save_preview:
            img_glyph.scale(4).save_png(out / "preview" / f"{digit}.png", gray=False)
    return saved
