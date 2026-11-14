"""Pengenalan layar sederhana (template matching) tanpa dependensi berat.

Cocok dipakai untuk tombol/ikon statis pada UI Lord Mobile. Bila OpenCV
terpasang, dipakai cv2.matchTemplate (lebih cepat & tahan skala); bila tidak,
dipakai fallback murni-Python berbasis selisih intensitas pada gambar kecil.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

try:  # opsional
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    HAS_CV = True
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    HAS_CV = False

from .device import Screen


@dataclass
class Gray:
    width: int
    height: int
    pixels: bytes

    def at(self, x: int, y: int) -> int:
        return self.pixels[y * self.width + x]

    def crop(self, x: int, y: int, w: int, h: int) -> "Gray":
        buf = bytearray(w * h)
        for j in range(h):
            src = (y + j) * self.width + x
            buf[j * w : (j + 1) * w] = self.pixels[src : src + w]
        return Gray(w, h, bytes(buf))


@dataclass
class Match:
    name: str
    score: float
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


# --------------------------------------------------------------------------- #
# Decoder PNG minimal (RGBA/RGB, 8-bit, non-interlaced) -> grayscale
# --------------------------------------------------------------------------- #
def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode_png_gray(data: bytes) -> Gray:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("bukan PNG")
    pos = 8
    width = height = bit_depth = color_type = interlace = 0
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
    if bit_depth != 8:
        raise ValueError(f"bit depth {bit_depth} belum didukung")
    if interlace:
        raise ValueError("PNG interlaced belum didukung")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError(f"color type {color_type} belum didukung (palette pakai cv2)")

    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = bytearray(width * height)
    prev = bytearray(stride)
    src = 0
    for y in range(height):
        ftype = raw[src]
        src += 1
        line = bytearray(raw[src : src + stride])
        src += stride
        if ftype == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                up_left = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(left, prev[i], up_left)) & 0xFF
        prev = line
        base = y * width
        for x in range(width):
            o = x * channels
            if channels >= 3:
                r, g, b = line[o], line[o + 1], line[o + 2]
                a = line[o + 3] if channels == 4 else 255
                gray = (r * 77 + g * 150 + b * 29) >> 8
                if a != 255:
                    gray = (gray * a + 255 * (255 - a)) // 255
            else:
                gray = line[o] if channels == 1 else line[o]
            out[base + x] = gray
    return Gray(width, height, bytes(out))


def to_gray(screen: Screen | bytes) -> "object":
    data = screen.data if isinstance(screen, Screen) else screen
    if HAS_CV:
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError("gambar tidak bisa didekode")
        return img
    return decode_png_gray(data)


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
def _match_cv(screen_img, tpl_img) -> Tuple[float, int, int]:
    """TM_CCOEFF_NORMED, dengan fallback TM_SQDIFF_NORMED untuk template polos.

    Template hampir seragam (tombol warna solid) membuat korelasi tidak stabil;
    untuk kasus itu selisih kuadrat ternormalisasi jauh lebih dapat diandalkan.
    """
    std = float(cv2.meanStdDev(tpl_img)[1][0][0])
    if std < 8.0:
        res = cv2.matchTemplate(screen_img, tpl_img, cv2.TM_SQDIFF_NORMED)
        minv, _, minloc, _ = cv2.minMaxLoc(res)
        return float(1.0 - minv), int(minloc[0]), int(minloc[1])
    res = cv2.matchTemplate(screen_img, tpl_img, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    return float(maxv), int(maxloc[0]), int(maxloc[1])


def _match_py(screen: Gray, tpl: Gray, coarse: int = 8) -> Tuple[float, int, int]:
    """Fallback tanpa OpenCV (jarang dipakai; OpenCV sangat disarankan).

    Strategi dua tahap agar tetap cepat di 1280x720:
      1. rough pass: sampling tiap `coarse` piksel untuk menemukan kandidat;
      2. refine pass: periksa ±coarse di sekitar kandidat terbaik.

    Catatan: skor pakai normalisasi pola (bukan selisih absolut) supaya
    konsisten dengan TM_CCOEFF_NORMED saat template punya kontras rendah.
    """
    if tpl.width >= screen.width or tpl.height >= screen.height:
        return 0.0, 0, 0

    tpl_step = max(1, min(4, tpl.width // 16, tpl.height // 16))
    tpl_vals = [
        tpl.pixels[j * tpl.width + i]
        for j in range(0, tpl.height, tpl_step)
        for i in range(0, tpl.width, tpl_step)
    ]
    n = len(tpl_vals)
    tpl_mean = sum(tpl_vals) / n
    tpl_dev = [v - tpl_mean for v in tpl_vals]
    tpl_norm = sum(d * d for d in tpl_dev) ** 0.5
    # Template hampir polos (tombol warna solid): korelasi tidak bermakna,
    # pakai kemiripan intensitas (1 - rata-rata selisih).
    flat = tpl_norm < 8.0

    def score_at(x: int, y: int) -> float:
        if flat:
            total = 0
            k = 0
            idx = 0
            for j in range(0, tpl.height, tpl_step):
                row = (y + j) * screen.width + x
                for i in range(0, tpl.width, tpl_step):
                    total += abs(screen.pixels[row + i] - tpl_vals[idx])
                    idx += 1
                    k += 1
            return 1.0 - (total / (k * 255.0)) if k else 0.0
        acc = 0.0
        se = 0.0
        k = 0
        for j in range(0, tpl.height, tpl_step):
            row = (y + j) * screen.width + x
            for i in range(0, tpl.width, tpl_step):
                v = screen.pixels[row + i]
                acc += v
                se += v * v
                k += 1
        if not k:
            return -1.0
        mean = acc / k
        var = se / k - mean * mean
        snorm = (var * k) ** 0.5 if var > 0 else 0.0
        if snorm <= 0:
            return 0.0
        num = 0.0
        idx = 0
        for j in range(0, tpl.height, tpl_step):
            row = (y + j) * screen.width + x
            for i in range(0, tpl.width, tpl_step):
                num += tpl_dev[idx] * (screen.pixels[row + i] - mean)
                idx += 1
        return num / (tpl_norm * snorm)

    best = (-2.0, 0, 0)
    for y in range(0, screen.height - tpl.height + 1, coarse):
        for x in range(0, screen.width - tpl.width + 1, coarse):
            sc = score_at(x, y)
            if sc > best[0]:
                best = (sc, x, y)
    sc0, bx, by = best
    for y in range(max(0, by - coarse), min(screen.height - tpl.height, by + coarse) + 1):
        for x in range(max(0, bx - coarse), min(screen.width - tpl.width, bx + coarse) + 1):
            sc = score_at(x, y)
            if sc > sc0:
                sc0, bx, by = sc, x, y
    return sc0, bx, by


class TemplateMatcher:
    def __init__(self, template_dir: str | Path, threshold: float = 0.86):
        self.dir = Path(template_dir)
        self.threshold = threshold
        self._cache: Dict[str, object] = {}

    def available(self) -> Dict[str, Path]:
        if not self.dir.exists():
            return {}
        return {p.stem: p for p in sorted(self.dir.glob("*.png"))}

    def load(self, name: str):
        if name in self._cache:
            return self._cache[name]
        path = self.dir / f"{name}.png"
        if not path.exists():
            return None
        data = path.read_bytes()
        if HAS_CV:
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            self._cache[name] = img
            return img
        tpl = decode_png_gray(data)
        self._cache[name] = tpl
        return tpl

    def find(self, screen: Screen, name: str, threshold: Optional[float] = None) -> Optional[Match]:
        tpl = self.load(name)
        if tpl is None:
            return None
        img = to_gray(screen)
        th = self.threshold if threshold is None else threshold
        if HAS_CV:
            score, x, y = _match_cv(img, tpl)
            h, w = tpl.shape[:2]
        else:
            score, x, y = _match_py(img, tpl)  # type: ignore[arg-type]
            h, w = tpl.height, tpl.width  # type: ignore[union-attr]
        if score < th:
            return None
        return Match(name, score, x, y, w, h)

    def find_any(self, screen: Screen, names, threshold: Optional[float] = None) -> Optional[Match]:
        best: Optional[Match] = None
        for n in names:
            m = self.find(screen, n, threshold)
            if m and (best is None or m.score > best.score):
                best = m
        return best

    def exists(self, screen: Screen, name: str, threshold: Optional[float] = None) -> bool:
        return self.find(screen, name, threshold) is not None


def ocr_numbers(screen: Screen, box: Tuple[float, float, float, float],
                template_dir="assets/ocr", min_score: float = 0.72) -> str:
    """Baca angka dari kotak fraksi layar memakai template offline 0-9."""
    from .imaging import decode_png
    from .ocr import DigitOCR

    img = decode_png(screen.data).crop_fraction(box)
    reader = DigitOCR(template_dir)
    return reader.read_image(img, min_score=min_score).text
