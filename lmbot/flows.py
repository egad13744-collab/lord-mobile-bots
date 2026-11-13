"""Flow navigasi UI berbasis YAML.

Satu flow = urutan langkah (tap / tap_text / wait / swipe / assert / type /
back). Ini memisahkan "di mana harus menekan" dari logika bisnis, sehingga
koordinat per-resolusi cukup ditulis sekali di config/flows/*.yaml dan bisa
dikoreksi user tanpa mengubah Python.

Contoh langkah:
  - tap: [0.50, 0.90]          # koordinat fraksi (0..1) -> aman beda resolusi
  - tap_text: open_bank        # ambil dari ui.* di settings.yaml
  - assert: bank_panel         # template harus terlihat (opsional)
  - wait: 1.5
  - type: "!bal"
  - back
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .device import BaseDriver
from .vision import TemplateMatcher


class FlowError(Exception):
    pass


@dataclass
class Step:
    kind: str
    value: Any
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Flow:
    name: str
    description: str = ""
    steps: List[Step] = field(default_factory=list)
    timeout: float = 15.0
    enabled: bool = True


# Langkah tanpa nilai: ditulis sebagai string ("- back") atau {back: true}.
VALUELESS_STEPS = {"back"}


def _parse_step(raw: Any) -> Step:
    if isinstance(raw, str):
        name = raw.strip().lower()
        if name in VALUELESS_STEPS:
            return Step(name, None)
        raise FlowError(f"langkah teks tidak dikenal: {raw!r}")
    if not isinstance(raw, dict) or len(raw) != 1:
        raise FlowError(f"langkah tidak valid: {raw!r}")
    (kind, value), = raw.items()
    if kind in VALUELESS_STEPS:
        return Step(kind, value)
    if kind not in {
        "tap", "tap_text", "wait", "swipe", "assert", "type", "back",
        "key", "screenshot", "if_template", "swipe_until", "wait_stable",
    }:
        raise FlowError(f"jenis langkah tidak dikenal: {kind}")
    return Step(kind, value)


def load_flow(path: str | Path) -> Flow:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    steps_raw = data.get("steps") or []
    steps: List[Step] = []
    for item in steps_raw:
        if isinstance(item, dict) and "tap" in item and isinstance(item["tap"], list):
            steps.append(Step("tap", list(item["tap"])))
            if "wait" in item:
                steps.append(Step("wait", item["wait"]))
            continue
        steps.append(_parse_step(item))
    return Flow(
        name=data.get("name") or p.stem,
        description=data.get("description", ""),
        steps=steps,
        timeout=float(data.get("timeout", 15.0)),
        enabled=bool(data.get("enabled", True)),
    )


def load_flows(directory: str | Path) -> Dict[str, Flow]:
    out: Dict[str, Flow] = {}
    d = Path(directory)
    if not d.exists():
        return out
    for p in sorted(d.glob("*.yaml")):
        flow = load_flow(p)
        out[flow.name] = flow
    return out


class FlowRunner:
    def __init__(
        self,
        driver: BaseDriver,
        cfg,
        matcher: Optional[TemplateMatcher] = None,
        logger=None,
    ):
        self.driver = driver
        self.cfg = cfg
        self.matcher = matcher
        self.log = logger
        self.ui = cfg.section("ui")

    # -- helper -- #
    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def point(self, value) -> tuple[int, int]:
        """Terima [fx, fy] fraksi atau [x, y] piksel."""
        if isinstance(value, str):
            named = self.ui.get(value)
            if not named:
                raise FlowError(f"ui.{value} tidak ada di settings.yaml")
            value = named
        x, y = value[0], value[1]
        if isinstance(x, float) and isinstance(y, float) and 0 <= x <= 1 and 0 <= y <= 1:
            return int(self.driver.width * x), int(self.driver.height * y)
        return int(x), int(y)

    def _assert_template(self, name: str, timeout: Optional[float] = None) -> bool:
        """Tunggu template muncul. Bila template belum pernah dibuat, jangan blokir
        (mode kalibrasi), tetapi catat peringatan sekali."""
        if not self.matcher:
            return True
        if not self.matcher.available().get(name):
            if not getattr(self, "_warned_missing", None):
                self._warned_missing = set()
            if name not in self._warned_missing:
                self._warned_missing.add(name)
                self._log(f"[flow] template '{name}' belum ada — assert dilewati")
            return True
        deadline = time.monotonic() + (timeout or self.cfg.get("flows.step_timeout", 15.0))
        while time.monotonic() < deadline:
            shot = self.driver.screenshot()
            if self.matcher.exists(shot, name):
                return True
            time.sleep(0.5)
        raise FlowError(f"template '{name}' tidak muncul di layar")

    def wait_for_frame(self, tries: int = 6, pause: float = 0.4) -> bool:
        """Pastikan layar 'stabil' (dua screenshot berturut identik)."""
        prev = None
        for _ in range(max(1, tries)):
            shot = self.driver.screenshot()
            blob = shot.data[:4096] + bytes([len(shot.data) % 251])
            if prev == blob:
                return True
            prev = blob
            time.sleep(pause)
        return False

    # -- eksekusi -- #
    def run(self, flow: Flow, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = context or {}
        self._log(f"[flow] {flow.name} ({len(flow.steps)} langkah)")
        for idx, step in enumerate(flow.steps, 1):
            self._run_step(step, ctx, idx)
        return ctx

    def run_named(self, name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        flows = load_flows(self.cfg.resolve_path(self.cfg.get("flows.dir", "config/flows")))
        if name not in flows:
            raise FlowError(f"flow '{name}' tidak ditemukan")
        return self.run(flows[name], context)

    def _run_step(self, step: Step, ctx: Dict[str, Any], idx: int) -> None:
        kind, val = step.kind, step.value
        if kind == "wait":
            time.sleep(float(val))
        elif kind == "wait_stable":
            self.wait_for_frame(tries=int(val) if isinstance(val, (int, float)) else 6)
        elif kind == "tap":
            x, y = self.point(val)
            self.driver.tap(x, y)
            time.sleep(float(ctx.get("tap_pause", 0.4)))
        elif kind == "tap_text":
            x, y = self.point(str(val))
            self.driver.tap(x, y)
            time.sleep(float(ctx.get("tap_pause", 0.4)))
        elif kind == "swipe":
            x1, y1, x2, y2 = val
            p1, p2 = self.point([x1, y1]), self.point([x2, y2])
            self.driver.swipe(p1[0], p1[1], p2[0], p2[1], int(ctx.get("swipe_ms", 400)))
            time.sleep(0.4)
        elif kind == "assert":
            timeout = None
            if isinstance(val, dict):
                timeout = val.get("timeout")
                val = val.get("template")
            self._assert_template(str(val), timeout)
        elif kind == "type":
            text = str(val)
            for key, real in ctx.items():
                text = text.replace("{" + key + "}", str(real))
            self.driver.text(text)
            time.sleep(float(ctx.get("type_pause", 0.8)))
        elif kind == "back":
            self.driver.keyevent(4)
            time.sleep(0.6)
        elif kind == "key":
            self.driver.keyevent(val)
            time.sleep(0.4)
        elif kind == "screenshot":
            shot = self.driver.screenshot()
            path = self.cfg.resolve_path(str(val))
            shot.save(path)
            self._log(f"  screenshot -> {path}")
        elif kind == "swipe_until":
            template = val["template"]
            direction = val.get("direction", "up")
            tries = int(val.get("tries", 4))
            for _ in range(tries):
                shot = self.driver.screenshot()
                if self.matcher and self.matcher.exists(shot, template):
                    return
                self._swipe_direction(direction)
                time.sleep(0.8)
            raise FlowError(f"swipe_until: '{template}' tidak ditemukan")
        elif kind == "if_template":
            template = val["template"]
            shot = self.driver.screenshot()
            if self.matcher and self.matcher.exists(shot, template):
                x, y = self.point(val["then"])
                self.driver.tap(x, y)
                time.sleep(0.5)
        else:  # pragma: no cover
            raise FlowError(f"langkah tidak didukung: {kind}")

    def _swipe_direction(self, direction: str) -> None:
        w, h = self.driver.width, self.driver.height
        if direction == "up":
            self.driver.swipe(w // 2, int(h * 0.75), w // 2, int(h * 0.3))
        elif direction == "down":
            self.driver.swipe(w // 2, int(h * 0.3), w // 2, int(h * 0.75))
        elif direction == "left":
            self.driver.swipe(int(w * 0.8), h // 2, int(w * 0.2), h // 2)
        else:
            self.driver.swipe(int(w * 0.2), h // 2, int(w * 0.8), h // 2)
