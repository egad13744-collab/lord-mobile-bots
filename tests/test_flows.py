"""Uji lapisan perangkat & flow tanpa emulator."""
from __future__ import annotations

import pytest

from lmbot.config import load_config
from lmbot.device import MockDriver
from lmbot.flows import Flow, FlowError, FlowRunner, Step, load_flows
from lmbot.vision import Gray, decode_png_gray


def test_mock_driver_records_actions():
    drv = MockDriver(1280, 720)
    drv.connect()
    drv.tap_fraction(0.5, 0.5)
    drv.text("!bal")
    assert drv.taps() == [("tap", 640, 360)]
    assert drv.texts() == ["!bal"]


def test_flow_runner_executes_steps(cfg_or_default=None):
    cfg = load_config()
    drv = MockDriver()
    runner = FlowRunner(drv, cfg)
    flow = Flow(
        name="t",
        steps=[
            Step("tap", [0.5, 0.5]),
            Step("wait", 0.0),
            Step("tap_text", "chat_input"),
            Step("type", "!bal"),
            Step("swipe", [0.5, 0.8, 0.5, 0.2]),
        ],
    )
    runner.run(flow, {"tap_pause": 0})
    kinds = [a[0] for a in drv.actions]
    assert kinds.count("tap") == 2
    assert "swipe" in kinds
    assert drv.texts() == ["!bal"]


def test_flow_context_substitution():
    cfg = load_config()
    drv = MockDriver()
    runner = FlowRunner(drv, cfg)
    runner.run(Flow("t", steps=[Step("type", "kirim {nick}")]), {"nick": "budi"})
    assert drv.texts() == ["kirim budi"]


def test_point_fraction_config():
    cfg = load_config()
    drv = MockDriver(1000, 500)
    runner = FlowRunner(drv, cfg)
    assert runner.point([0.5, 0.2]) == (500, 100)
    assert runner.point("chat_input") == (500, int(500 * 0.86))


def test_load_bundled_flows():
    cfg = load_config()
    flows = load_flows(cfg.resolve_path("config/flows"))
    assert "chat_open" in flows and "bank_open_member" in flows
    assert all(f.steps for f in flows.values())


def test_flow_invalid_kind(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text("name: x\nsteps:\n  - teleport: [1, 2]\n", encoding="utf-8")
    with pytest.raises(FlowError):
        load_flows(tmp_path)


def test_gray_helpers():
    g = Gray(4, 3, bytes(range(12)))
    assert g.at(1, 1) == 5
    assert g.crop(1, 1, 2, 2).pixels == bytes([5, 6, 9, 10])


def test_decode_png_minimal():
    """PNG 2x2 grayscale buatan sendiri: validasi decoder fallback."""
    import struct
    import zlib

    w = h = 2
    raw = b""
    for y in range(h):
        raw += b"\x00" + bytes([10 * (y + 1), 20 * (y + 1)])
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    g = decode_png_gray(png)
    assert (g.width, g.height) == (2, 2)
    assert g.pixels == bytes([10, 20, 20, 40])
