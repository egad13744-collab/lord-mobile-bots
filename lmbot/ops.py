"""Operasi tingkat-tinggi terhadap game.

Handler perintah TIDAK menyentuh koordinat layar. Mereka memanggil metode di
sini, dan kelas inilah yang menerjemahkannya ke flow YAML + driver ADB.
Dengan begitu alur bisa diuji penuh lewat MockOps tanpa emulator.

Dua implementasi:
  * AdbOps  — menggerakkan MuMu lewat ADB (screenshot -> tap -> ketik).
  * MockOps — mencatat panggilan; dipakai `--dry-run` dan unit test.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .device import BaseDriver, DeviceError
from .flows import FlowError, FlowRunner, load_flows
from .vision import TemplateMatcher


class OpsError(Exception):
    """Operasi tidak bisa dilakukan (flow belum dikonfigurasi, dsb.)."""


@dataclass
class ChatLine:
    sender: str
    text: str
    ts: float = field(default_factory=time.time)


class GameOps:
    """Kontrak operasi. Implementasi wajib menyediakan semua metode."""

    def open_chat(self) -> None: ...
    def close_chat(self) -> None: ...
    def send_chat(self, message: str) -> None: ...
    def read_chat(self) -> List[ChatLine]: ...
    def in_guild_map(self) -> bool: ...
    def open_bank_panel(self, nick: str) -> None: ...
    def send_rss_to_member(self, nick: str, rss: Dict[str, int]) -> None: ...
    def run_action(self, action: str, params: Optional[Dict[str, Any]] = None) -> None: ...
    def screenshot(self, path: str) -> None: ...


# --------------------------------------------------------------------------- #
# Mock
# --------------------------------------------------------------------------- #
class MockOps(GameOps):
    def __init__(self, script: Optional[List[str]] = None):
        self.calls: List[tuple] = []
        self.outbox: List[str] = []
        self.script = list(script or [])
        self._script_idx = 0

    def _rec(self, *args) -> None:
        self.calls.append(args)

    def open_chat(self) -> None:
        self._rec("open_chat")

    def close_chat(self) -> None:
        self._rec("close_chat")

    def send_chat(self, message: str) -> None:
        self._rec("send_chat", message)
        self.outbox.append(message)

    def read_chat(self) -> List[ChatLine]:
        self._rec("read_chat")
        if self._script_idx < len(self.script):
            item = self.script[self._script_idx]
            self._script_idx += 1
            if isinstance(item, str) and ":" in item:
                sender, _, text = item.partition(":")
                return [ChatLine(sender.strip(), text.strip())]
            return [ChatLine("lady_ayu", str(item))]
        return []

    def in_guild_map(self) -> bool:
        self._rec("in_guild_map")
        return True

    def open_bank_panel(self, nick: str) -> None:
        self._rec("open_bank_panel", nick)

    def send_rss_to_member(self, nick: str, rss: Dict[str, int]) -> None:
        self._rec("send_rss_to_member", nick, dict(rss))

    def run_action(self, action: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._rec("run_action", action, dict(params or {}))

    def screenshot(self, path: str) -> None:
        self._rec("screenshot", path)

    def actions(self) -> List[str]:
        return [c[1] for c in self.calls if c[0] == "run_action"]


class DryRunOps(MockOps):
    """Bungkus ops asli: semua aksi dicatat, tidak ada yang sampai ke emulator."""

    def __init__(self, inner: Optional[GameOps] = None, logger=None):
        super().__init__()
        self.inner = inner
        self.logger = logger

    def _rec(self, *args) -> None:
        super()._rec(*args)
        if self.logger:
            self.logger(f"[dry-run] {args[0]} {args[1:] if len(args) > 1 else ''}".rstrip())

    def read_chat(self):
        if self.inner:
            try:
                return self.inner.read_chat()
            except OpsError:
                return []
        return []

    def in_guild_map(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# ADB
# --------------------------------------------------------------------------- #
class AdbOps(GameOps):
    BANK_FLOW = "guild_bank"
    CHAT_FLOW = "chat_send"

    def __init__(self, cfg, driver: BaseDriver, logger=None, matcher: Optional[TemplateMatcher] = None):
        self.cfg = cfg
        self.driver = driver
        self.log = logger
        self.matcher = matcher or TemplateMatcher(
            cfg.resolve_path(cfg.get("templates.dir", "assets/templates")),
            float(cfg.get("templates.threshold", 0.86)),
        )
        self.runner = FlowRunner(driver, cfg, self.matcher, logger)
        self.flows = load_flows(cfg.resolve_path(cfg.get("flows.dir", "config/flows")))
        self._chat_open = False

    # -- util -- #
    def _flow(self, name: str):
        flow = self.flows.get(name)
        if not flow:
            raise OpsError(
                f"flow '{name}' belum ada di config/flows/. Lihat docs/CALIBRATION.md "
                f"untuk cara merekam koordinat tombol."
            )
        if not flow.enabled:
            raise OpsError(
                f"flow '{name}' masih dinonaktifkan (enabled: false). Kalibrasi "
                f"koordinatnya dulu lalu set enabled: true — lihat docs/CALIBRATION.md"
            )
        return flow

    def _run(self, name: str, ctx: Optional[dict] = None) -> None:
        try:
            self.runner.run(self._flow(name), ctx)
        except FlowError as exc:
            raise OpsError(f"flow '{name}' gagal: {exc}") from exc
        except DeviceError as exc:
            raise OpsError(f"perangkat error saat flow '{name}': {exc}") from exc

    # -- chat -- #
    def open_chat(self) -> None:
        if self._chat_open:
            return
        self._run("chat_open")
        self._chat_open = True
        time.sleep(float(self.cfg.get("ui.chat_open_wait", 1.2)))

    def close_chat(self) -> None:
        if not self._chat_open:
            return
        try:
            self.driver.tap_fraction(*self.cfg.get("ui.chat_close", [0.94, 0.14]))
        finally:
            self._chat_open = False

    def send_chat(self, message: str) -> None:
        self.open_chat()
        self.driver.tap_fraction(*self.cfg.get("ui.chat_input", [0.5, 0.86]))
        time.sleep(0.4)
        self.driver.text(message)
        time.sleep(0.3)
        self.driver.tap_fraction(*self.cfg.get("ui.chat_send", [0.94, 0.86]))
        time.sleep(float(self.cfg.get("ui.chat_reply_wait", 2.0)))

    def read_chat(self) -> List[ChatLine]:
        """Ambil baris chat baru.

        Membutuhkan OCR teks (lihat docs/OCR.md). Bila OCR tidak tersedia,
        bot tetap bisa menerima perintah via stdin/file/webhook (lihat
        lmbot/chat.py) — jadi fitur tidak hilang, hanya sumbernya berbeda.
        """
        raise OpsError(
            "pembacaan chat dari layar butuh OCR. Pakai sumber perintah lain: "
            "`lmbot ui` (ketik langsung), `--source file`, atau `--source http`. "
            "Detail: docs/OCR.md"
        )

    # -- game -- #
    def in_guild_map(self) -> bool:
        name = "guild_map"
        if not self.matcher.available().get(name):
            return True  # template belum ada -> jangan blokir
        try:
            shot = self.driver.screenshot()
        except DeviceError:
            return False
        return self.matcher.exists(shot, name)

    def open_bank_panel(self, nick: str) -> None:
        self._run("bank_open_member", {"nick": nick})

    def send_rss_to_member(self, nick: str, rss: Dict[str, int]) -> None:
        ctx: Dict[str, Any] = {"nick": nick, "rss": json.dumps(rss)}
        for key in ("food", "stone", "wood", "ore", "gold"):
            ctx[f"amount_{key}"] = str(int(rss.get(key, 0) or 0))
        self._run("bank_send_rss", ctx)

    def run_action(self, action: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._run(action, dict(params or {}))

    def screenshot(self, path: str) -> None:
        self.driver.screenshot().save(self.cfg.resolve_path(path))
