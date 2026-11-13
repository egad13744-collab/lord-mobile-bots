"""Uji crop/resize/template dari screenshot (tanpa emulator, tanpa OpenCV wajib)."""
from __future__ import annotations

import pytest

from lmbot.imaging import (
    Image,
    ImageError,
    box_to_pixels,
    decode_png,
    encode_png,
    list_templates,
    load_image,
    make_template,
    missing_templates,
    parse_box,
    verify_template,
)


def _fake_screen(w=320, h=180, box=None) -> Image:
    px = bytearray(w * h * 3)
    for i in range(w * h):
        px[i * 3] = (i * 7) % 256
        px[i * 3 + 1] = (i * 13) % 256
        px[i * 3 + 2] = 90
    img = Image(w, h, 3, bytes(px))
    if box:
        x0, y0, x1, y1 = box
        data = bytearray(img.data)
        for y in range(y0, y1):
            for x in range(x0, x1):
                o = (y * w + x) * 3
                data[o : o + 3] = b"\x14\xdc\x78"
        img = Image(w, h, 3, bytes(data))
    return img


@pytest.fixture()
def screen(tmp_path):
    path = tmp_path / "screen.png"
    path.write_bytes(encode_png(_fake_screen(box=(100, 80, 160, 120))))
    return path


def test_png_roundtrip():
    img = _fake_screen(9, 5)
    back = decode_png(encode_png(img))
    assert (back.width, back.height, back.channels) == (9, 5, 3)
    assert back.data == img.data


def test_crop_and_scale(screen):
    img = load_image(screen)
    crop = img.crop(10, 20, 40, 30)
    assert (crop.width, crop.height) == (40, 30)
    small = crop.resize(20, 15)
    assert (small.width, small.height) == (20, 15)
    assert len(small.data) == 20 * 15 * 3


def test_parse_box_and_fraction():
    assert parse_box("0.1,0.2,0.3,0.4") == [0.1, 0.2, 0.3, 0.4]
    assert box_to_pixels([0.5, 0.5, 0.1, 0.1], 1000, 500) == (500, 250, 100, 50)
    assert box_to_pixels([10, 20, 30, 40], 1000, 500) == (10, 20, 30, 40)
    with pytest.raises(ImageError):
        parse_box("1,2,3")


def test_make_template_and_verify(screen, tmp_path):
    tdir = tmp_path / "templates"
    res = make_template(screen, "send_button", [100, 80, 60, 40], tdir)
    assert res.path.exists() and res.template_size == (60, 40)
    assert res.box_px == (100, 80, 60, 40)
    assert res.box_fraction[0] == pytest.approx(100 / 320, abs=1e-3)

    found = verify_template(screen, "send_button", tdir)
    assert found["found"] is True
    assert found["score"] > 0.86
    assert found["center_fraction"][0] == pytest.approx(130 / 320, abs=0.01)

    status = list_templates(tdir)
    assert status["send_button"] and not status["bank_panel"]
    assert "bank_panel" in missing_templates(tdir)


def test_make_template_scaled(screen, tmp_path):
    res = make_template(screen, "t", [0.3, 0.4, 0.2, 0.2], tmp_path / "tpl", scale=0.5)
    assert res.template_size[0] == 32  # 0.2*320=64 -> 50%
    again = verify_template(screen, "t", tmp_path / "tpl", threshold=0.5)
    assert "score" in again


def test_make_template_max_width(screen, tmp_path):
    res = make_template(screen, "wide", [0.1, 0.1, 0.5, 0.5], tmp_path / "tpl", max_width=64)
    assert res.template_size[0] == 64
    assert res.template_size[1] < 64


def test_invalid_image(tmp_path):
    bogus = tmp_path / "x.bmp"
    bogus.write_bytes(b"bukan gambar")
    with pytest.raises(ImageError):
        load_image(bogus)
