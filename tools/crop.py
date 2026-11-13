#!/usr/bin/env python3
"""Crop cepat: ambil area dari screenshot dan simpan (template atau sekedar lihat).

Contoh:
  python tools/crop.py screen.png --box 0.62,0.10,0.78,0.16 --out logs/crop.png
  python tools/crop.py screen.png --box 793,72,998,115 --out assets/templates/send_button.png
  python tools/crop.py screen.png --box 0.6,0.8,0.8,0.9 --out logs/x.png --scale 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lmbot.imaging import ImageError, box_to_pixels, load_png, parse_box


def main() -> int:
    ap = argparse.ArgumentParser(description="crop area dari screenshot")
    ap.add_argument("image")
    ap.add_argument("--box", required=True, help="x,y,w,h (fraksi 0..1 atau piksel)")
    ap.add_argument("--out", default="logs/crop.png")
    ap.add_argument("--scale", type=float, default=1.0, help="perkecil (<1) / perbesar (>1)")
    ap.add_argument("--color", action="store_true", help="simpan RGB (default grayscale)")
    ap.add_argument("--max-width", type=int, default=0)
    args = ap.parse_args()

    try:
        img = load_png(args.image)
        x, y, w, h = box_to_pixels(parse_box(args.box), img.width, img.height)
        crop = img.crop(x, y, w, h)
        if args.max_width and crop.width > args.max_width:
            crop = crop.resize(args.max_width, max(1, int(crop.height * args.max_width / crop.width)))
        if abs(args.scale - 1.0) > 1e-9:
            crop = crop.scale(args.scale)
    except (ImageError, OSError) as exc:
        print(f"gagal: {exc}")
        return 1

    path = crop.save_png(args.out, gray=not args.color)
    print(f"sumber  : {args.image} ({img.width}x{img.height})")
    print(f"crop px : x={x} y={y} w={w} h={h}")
    print(f"fraksi  : {x/img.width:.4f}, {y/img.height:.4f}, {w/img.width:.4f}, {h/img.height:.4f}")
    print(f"tengah  : tap: [{x + w/2:.0f} px = {(x+w/2)/img.width:.4f}, {(y+h/2)/img.height:.4f}]")
    print(f"hasil   : {path} ({crop.width}x{crop.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
