"""Pengolahan gambar untuk membuat template dari screenshot mentah.

Dipakai subcommand `lmbot template`: ambil screenshot fullscreen dari user,
crop satu area (fraksi layar), kecilkan, lalu simpan sebagai PNG template di
`assets/templates/`. Tidak butuh PIL/OpenCV — dekoder & enkoder PNG minimal
sudah ada di `vision.py`.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

try:  # opsional: dukung JPEG/WebP/PNG-16bit dari screenshot HP
    from PIL import Image as _PILImage  # type: ignore

    HAS_PIL = True
except Exception:  # pragma: no cover
    _PILImage = None  # type: ignore
    HAS_PIL = False

# Template yang dipakai bot; urutan ini juga dipakai `lmbot template list`.
EXPECTED_TEMPLATES: Dict[str, str] = {
    "main_map": "peta utama (untuk memastikan game tidak di menu lain)",
    "guild_map": "peta klan / castle bank",
    "guild_menu": "menu klan (tombol Bank, Member, dst.)",
    "bank_panel": "panel bank klan terbuka (judul/tab bank)",
    "bank_food_tab": "tab/kategori Food di panel bank",
    "bank_stone_tab": "tab Stone di panel bank",
    "bank_wood_tab": "tab Wood di panel bank",
    "bank_ore_tab": "tab Ore di panel bank",
    "bank_gold_tab": "tab Gold di panel bank",
    "search_member": "kolom pencarian member",
    "member_row": "baris hasil pencarian member",
    "send_button": "tombol Kirim/Transfer",
    "popup_ok": "tombol OK pada dialog konfirmasi",
    "chat_panel": "panel chat in-game terbuka",
}

# Rentang skor yang dianggap wajar saat verifikasi template.
MIN_OK_SCORE = 0.55
GOOD_SCORE = 0.75


class ImageError(Exception):
    pass


@dataclass
class Image:
    width: int
    height: int
    channels: int  # 1 (gray), 2 (gray+alpha), 3 (rgb), 4 (rgba)
    data: bytes

    # ---------------- dasar ---------------- #
    def at(self, x: int, y: int) -> Tuple[int, ...]:
        o = (y * self.width + x) * self.channels
        return tuple(self.data[o : o + self.channels])

    def crop(self, x: int, y: int, w: int, h: int) -> "Image":
        if w <= 0 or h <= 0:
            raise ImageError("ukuran crop harus > 0")
        x = max(0, min(x, self.width - 1))
        y = max(0, min(y, self.height - 1))
        w = min(w, self.width - x)
        h = min(h, self.height - y)
        stride = self.channels
        out = bytearray(w * h * stride)
        for j in range(h):
            src = ((y + j) * self.width + x) * stride
            out[j * w * stride : (j + 1) * w * stride] = self.data[src : src + w * stride]
        return Image(w, h, stride, bytes(out))

    def crop_fraction(self, box: Sequence[float]) -> "Image":
        x, y, w, h = box_to_pixels(box, self.width, self.height)
        return self.crop(x, y, w, h)

    def resize(self, width: int, height: int) -> "Image":
        """Box filter (rata-rata area) — bagus untuk memperkecil, aman untuk memperbesar."""
        if width <= 0 or height <= 0:
            raise ImageError("ukuran hasil harus > 0")
        if (width, height) == (self.width, self.height):
            return self
        ch = self.channels
        out = bytearray(width * height * ch)
        x_ratio = self.width / width
        y_ratio = self.height / height
        for j in range(height):
            y0 = int(j * y_ratio)
            y1 = max(y0 + 1, int((j + 1) * y_ratio))
            for i in range(width):
                x0 = int(i * x_ratio)
                x1 = max(x0 + 1, int((i + 1) * x_ratio))
                acc = [0] * ch
                n = 0
                for yy in range(y0, min(y1, self.height)):
                    row = yy * self.width
                    for xx in range(x0, min(x1, self.width)):
                        o = (row + xx) * ch
                        for c in range(ch):
                            acc[c] += self.data[o + c]
                        n += 1
                o = (j * width + i) * ch
                for c in range(ch):
                    out[o + c] = acc[c] // n if n else 0
        return Image(width, height, ch, bytes(out))

    def scale(self, factor: float) -> "Image":
        if factor <= 0:
            raise ImageError("faktor skala harus > 0")
        if abs(factor - 1.0) < 1e-9:
            return self
        return self.resize(max(1, int(self.width * factor)), max(1, int(self.height * factor)))

    def to_gray(self) -> "Image":
        if self.channels in (1, 2):
            return self if self.channels == 1 else Image(
                self.width, self.height, 1,
                bytes(self.data[i * 2] for i in range(self.width * self.height)),
            )
        ch = self.channels
        out = bytearray(self.width * self.height)
        for i in range(self.width * self.height):
            o = i * ch
            r, g, b = self.data[o], self.data[o + 1], self.data[o + 2]
            if ch == 4:
                a = self.data[o + 3]
                if a != 255:
                    r = (r * a + 255 * (255 - a)) // 255
                    g = (g * a + 255 * (255 - a)) // 255
                    b = (b * a + 255 * (255 - a)) // 255
            out[i] = (r * 77 + g * 150 + b * 29) >> 8
        return Image(self.width, self.height, 1, bytes(out))

    def save_png(self, path: str | Path, gray: bool = True) -> Path:
        img = self.to_gray() if gray and self.channels != 1 else self
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(encode_png(img))
        return p


# --------------------------------------------------------------------------- #
# box helpers
# --------------------------------------------------------------------------- #
def parse_box(text: str) -> List[float]:
    """'0.62,0.10,0.78,0.16' -> [x,y,w,h] (fraksi) atau piksel bila ada nilai >1."""
    parts = [p for p in text.replace(";", ",").split(",") if p.strip()]
    if len(parts) != 4:
        raise ImageError("box harus 4 angka: x1,y1,x2,y2 (fraksi) atau x,y,w,h (piksel)")
    return [float(p) for p in parts]


def box_to_pixels(box: Sequence[float], img_w: int, img_h: int) -> Tuple[int, int, int, int]:
    """Terima [x,y,w,h] fraksi (0..1) atau piksel absolut."""
    x, y, a, b = [float(v) for v in box]
    if max(x, y, a, b) <= 1.0:  # fraksi
        return (int(x * img_w), int(y * img_h), max(1, int(a * img_w)), max(1, int(b * img_h)))
    return int(x), int(y), max(1, int(a)), max(1, int(b))


def px_to_fraction(px: int, total: int) -> float:
    return round(px / total, 4) if total else 0.0


# --------------------------------------------------------------------------- #
# PNG decode / encode (minimal, tanpa dependensi)
# --------------------------------------------------------------------------- #
def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode_png(data: bytes) -> Image:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ImageError("bukan PNG (JPEG? konversi dulu atau pakai tools/crop.py)")
    pos = 8
    width = height = depth = ctype = interlace = 0
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    if depth != 8:
        raise ImageError(f"bit depth {depth} belum didukung (pakai 8-bit)")
    if interlace:
        raise ImageError("PNG interlaced belum didukung")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(ctype)
    if channels is None:
        raise ImageError(f"color type {ctype} belum didukung (palette)")

    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = bytearray(width * height * channels)
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
        out[y * stride : (y + 1) * stride] = line
        prev = line
    return Image(width, height, channels, bytes(out))


def _chunk(tag: bytes, body: bytes) -> bytes:
    return (
        struct.pack(">I", len(body))
        + tag
        + body
        + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    )


def encode_png(img: Image) -> bytes:
    ch = img.channels
    color_type = {1: 0, 2: 4, 3: 2, 4: 6}[ch]
    stride = img.width * ch
    raw = bytearray()
    for y in range(img.height):
        raw.append(0)  # filter none
        raw += img.data[y * stride : (y + 1) * stride]
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", img.width, img.height, 8, color_type, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def load_image(path: str | Path) -> "Image":
    """Muat gambar apa pun. PNG native selalu bisa; JPEG/WebP butuh Pillow."""
    p = Path(path)
    data = p.read_bytes()
    if data.startswith(b"\x89PNG"):
        try:
            return decode_png(data)
        except ImageError:
            if not HAS_PIL:
                raise
    if not HAS_PIL:
        raise ImageError(
            f"format {p.suffix} butuh Pillow. Install: pip install pillow — "
            "atau kirim screenshot dalam format PNG."
        )
    try:
        with _PILImage.open(p) as im:  # type: ignore[union-attr]
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            ch = len(im.getbands())
            return Image(im.width, im.height, ch, im.tobytes())
    except Exception as exc:  # PIL melempar berbagai tipe
        raise ImageError(f"gambar tidak bisa dibaca ({p.name}): {exc}") from exc


def load_png(path: str | Path) -> "Image":
    """Alias lama; sekarang menerima JPEG juga bila Pillow tersedia."""
    return load_image(path)


# --------------------------------------------------------------------------- #
# Alur utama: screenshot -> template
# --------------------------------------------------------------------------- #
@dataclass
class TemplateResult:
    name: str
    path: Path
    box_px: Tuple[int, int, int, int]
    box_fraction: Tuple[float, float, float, float]
    source_size: Tuple[int, int]
    template_size: Tuple[int, int]
    score: float = 0.0


def make_template(
    screen_path: str | Path,
    name: str,
    box: Sequence[float],
    template_dir: str | Path,
    gray: bool = True,
    scale: float = 1.0,
    max_width: int = 0,
    preview: bool = False,
) -> TemplateResult:
    """Crop `box` dari screenshot lalu simpan sebagai template PNG.

    box: [x, y, w, h] dalam fraksi (0..1) atau piksel.
    scale: <1 memperkecil (mis. 0.5), 1 = ukuran asli.
    max_width: batasi lebar template (piksel); 0 = tanpa batas.
    """
    img = load_png(screen_path)
    x, y, w, h = box_to_pixels(box, img.width, img.height)
    crop = img.crop(x, y, w, h)
    if max_width and crop.width > max_width:
        ratio = max_width / crop.width
        crop = crop.resize(max_width, max(1, int(crop.height * ratio)))
    if abs(scale - 1.0) > 1e-9:
        crop = crop.scale(scale)
    out_dir = Path(template_dir)
    path = crop.save_png(out_dir / f"{name}.png", gray=gray)
    if preview:
        crop.save_png(out_dir.parent / "preview" / f"{name}.png", gray=False)
    frac = (
        px_to_fraction(x, img.width),
        px_to_fraction(y, img.height),
        px_to_fraction(w, img.width),
        px_to_fraction(h, img.height),
    )
    return TemplateResult(
        name=name,
        path=path,
        box_px=(x, y, w, h),
        box_fraction=frac,
        source_size=(img.width, img.height),
        template_size=(crop.width, crop.height),
    )


def template_center_fraction(box_px: Tuple[int, int, int, int], w: int, h: int) -> Tuple[float, float]:
    """Titik tengah crop dalam fraksi layar — siap dipakai sebagai `tap:` di flow."""
    x, y, cw, chh = box_px
    return (px_to_fraction(x + cw // 2, w), px_to_fraction(y + chh // 2, h))


def verify_template(screen_path: str | Path, name: str, template_dir: str | Path,
                    threshold: float = 0.86) -> Dict[str, object]:
    """Cek apakah template `name` ditemukan pada screenshot (skor + posisi)."""
    from .device import Screen
    from .vision import TemplateMatcher

    img = load_png(screen_path)
    gray_bytes = encode_png(img.to_gray())
    screen = Screen(img.width, img.height, gray_bytes, "png")
    matcher = TemplateMatcher(template_dir, threshold)
    match = matcher.find(screen, name, threshold=0.0)
    if not match:
        return {"name": name, "found": False, "score": 0.0, "reason": "template tidak ada"}
    cx, cy = match.center
    return {
        "name": name,
        "found": match.score >= threshold,
        "score": round(match.score, 4),
        "center_px": (cx, cy),
        "center_fraction": (px_to_fraction(cx, img.width), px_to_fraction(cy, img.height)),
        "problematic": match.score < MIN_OK_SCORE,
        "threshold": threshold,
    }


def list_templates(template_dir: str | Path) -> Dict[str, bool]:
    d = Path(template_dir)
    existing = {p.stem for p in d.glob("*.png")} if d.exists() else set()
    return {name: name in existing for name in EXPECTED_TEMPLATES}


def missing_templates(template_dir: str | Path) -> List[str]:
    return [n for n, ok in list_templates(template_dir).items() if not ok]
