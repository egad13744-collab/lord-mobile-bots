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
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .device import BaseDriver, DeviceError
from .flows import FlowError, FlowRunner, load_flows
from .vision import TemplateMatcher

# Satu lock global: hanya satu alur yang boleh menyentuh layar pada satu waktu.
# Ini mencegah REPL, webhook, dan loop chat saling menimpa tap.
DEVICE_LOCK = threading.RLock()


def _with_lock(fn):
    def wrapper(*args, **kwargs):
        with DEVICE_LOCK:
            return fn(*args, **kwargs)

    wrapper.__name__ = getattr(fn, "__name__", "wrapped")
    wrapper.__doc__ = fn.__doc__
    return wrapper


class OpsError(Exception):
    """Operasi tidak bisa dilakukan (flow belum dikonfigurasi, dsb.)."""


@dataclass
class ChatLine:
    sender: str
    text: str
    ts: float = field(default_factory=time.time)


class GameOps:
    """Kontrak operasi. Implementasi wajib menyediakan semua metode."""

    @_with_lock
    def open_chat(self) -> None: ...
    @_with_lock
    def close_chat(self) -> None: ...
    @_with_lock
    def send_chat(self, message: str) -> None: ...
    def read_chat(self) -> List[ChatLine]: ...
    def in_guild_map(self) -> bool: ...
    @_with_lock
    def open_bank_panel(self, nick: str) -> None: ...
    @_with_lock
    def send_rss_to_member(self, nick: str, rss: Dict[str, int]) -> None: ...
    @_with_lock
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

    @_with_lock
    def open_chat(self) -> None:
        self._rec("open_chat")

    @_with_lock
    def close_chat(self) -> None:
        self._rec("close_chat")

    @_with_lock
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
            return [ChatLine("arken_ega", str(item))]
        return []

    def in_guild_map(self) -> bool:
        self._rec("in_guild_map")
        return True

    @_with_lock
    def open_bank_panel(self, nick: str) -> None:
        self._rec("open_bank_panel", nick)

    @_with_lock
    def send_rss_to_member(self, nick: str, rss: Dict[str, int]) -> None:
        self._rec("send_rss_to_member", nick, dict(rss))

    @_with_lock
    def run_action(self, action: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._rec("run_action", action, dict(params or {}))

    def screenshot(self, path: str) -> None:
        self._rec("screenshot", path)

    def actions(self) -> List[str]:
        return [c[1] for c in self.calls if c[0] == "run_action"]


class DryRunOps(MockOps):
    """Bungkus ops asli: semua aksi dicatat, tidak ada yang sampai ke emulator.

    Catatan: meski `inner` diberikan, metode aksi sengaja TIDAK diteruskan ke
    inner — dry-run harus 100% aman. Hanya pembacaan chat yang diteruskan
    supaya `--source chat --dry-run` tetap bisa mendengar perintah.
    """

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

    def __init__(self, cfg, driver: BaseDriver, logger=None, matcher: Optional[TemplateMatcher] = None, alerts=None):
        self.cfg = cfg
        self.driver = driver
        self.log = logger
        self.alerts = alerts
        self.matcher = matcher or TemplateMatcher(
            cfg.resolve_path(cfg.get("templates.dir", "assets/templates")),
            float(cfg.get("templates.threshold", 0.86)),
        )
        self.runner = FlowRunner(driver, cfg, self.matcher, logger)
        self.flows = load_flows(cfg.resolve_path(cfg.get("flows.dir", "config/flows")))
        self._chat_open = False
        self.min_confidence = float(cfg.get("vision.min_confidence", 0.5))
        self.max_retries = int(cfg.get("flows.max_retries", 1))
        self._last_screen: Optional[Any] = None
        self._last_screen_ts: float = 0.0
        self._chat_seen_key = ""
        self._chat_seen_lines = 0

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

    def _alert(self, title: str, detail: str, level: str = "warn", **extra) -> None:
        if self.alerts:
            self.alerts.send(level, title, detail, **extra)

    def _run(self, name: str, ctx: Optional[dict] = None) -> None:
        with DEVICE_LOCK:
            flow = self._flow(name)
            attempts = self.max_retries + 1
            last: Optional[Exception] = None
            for attempt in range(1, attempts + 1):
                try:
                    self.runner.run(flow, ctx)
                    return
                except FlowError as exc:
                    last = exc
                except DeviceError as exc:
                    last = exc
                except ValueError as exc:  # screenshot korup / bukan PNG
                    last = exc
                if attempt < attempts:
                    self._alert(
                        f"flow {name} percobaan {attempt} gagal",
                        str(last), level="info", flow=name,
                    )
                    self._recover_screen()
                    time.sleep(1.0 * attempt)
            self._alert(f"flow {name} gagal total", str(last), level="error", flow=name)
            if isinstance(last, (DeviceError, ValueError)):
                raise OpsError(f"perangkat error saat flow '{name}': {last}") from last
            raise OpsError(f"flow '{name}' gagal: {last}") from last

    # -- pemulihan layar -- #
    def _recover_screen(self) -> None:
        """Tutup popup/panel yang menggantung: tekan back 1x, lalu cek."""
        try:
            self._chat_open = False
            self.driver.keyevent(4)
            time.sleep(0.8)
        except DeviceError:
            pass

    def current_screen(self, template_names: Optional[List[str]] = None) -> Optional[str]:
        """Nama template pertama yang cocok dengan layar sekarang (None bila tak jelas)."""
        names = template_names or [
            "main_map", "guild_map", "guild_menu", "bank_panel", "chat_panel", "popup_ok",
        ]
        known = [n for n in names if self.matcher.available().get(n)]
        if not known:
            return None
        shot = self.driver.screenshot()
        for name in known:
            m = self.matcher.find(shot, name)
            if m and m.score >= self.min_confidence:
                return name
        return None

    def close_popup(self) -> bool:
        """Tutup popup/dialog 'OK' bila terdeteksi. True bila ada yang ditutup."""
        if not self.matcher.available().get("popup_ok"):
            return False
        shot = self.driver.screenshot()
        m = self.matcher.find(shot, "popup_ok")
        if not m:
            return False
        self.driver.tap(*m.center)
        time.sleep(0.6)
        return True

    # -- chat -- #
    @_with_lock
    def open_chat(self) -> None:
        if self._chat_open:
            return
        self._run("chat_open")
        self._chat_open = True
        time.sleep(float(self.cfg.get("ui.chat_open_wait", 1.2)))

    @_with_lock
    def close_chat(self) -> None:
        if not self._chat_open:
            return
        try:
            self.driver.tap_fraction(*self.cfg.get("ui.chat_close", [0.94, 0.14]))
        finally:
            self._chat_open = False

    @_with_lock
    def send_chat(self, message: str) -> None:
        self.open_chat()
        self.driver.tap_fraction(*self.cfg.get("ui.chat_input", [0.5, 0.86]))
        time.sleep(0.4)
        self.driver.text(message)
        time.sleep(0.3)
        self.driver.tap_fraction(*self.cfg.get("ui.chat_send", [0.94, 0.86]))
        time.sleep(float(self.cfg.get("ui.chat_reply_wait", 2.0)))

    def read_chat(self) -> List[ChatLine]:
        """Ambil balasan chat in-game yang baru.

        Sumber: `ui.chat_tail` — file teks yang diisi OCR/proxy/bridge lokal
        (format per baris: `nick: !perintah`). Bila OCR native belum aktif,
        bot tetap menerima perintah via terminal/file/webhook.
        """
        tail = self.cfg.get("ui.chat_tail")
        if not tail:
            raise OpsError(
                "chat_tail belum diatur. Isi ui.chat_tail di settings.yaml dengan file "
                "yang memuat baris 'nick: !perintah' (lihat docs/OCR.md), atau pakai "
                "sumber perintah terminal/file/http."
            )
        path = self.cfg.resolve_path(str(tail))
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        key = f"{len(text)}:{text[-64:]}"
        if key == self._chat_seen_key:
            return []
        self._chat_seen_key = key
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        new_lines = lines[self._chat_seen_lines:]
        self._chat_seen_lines = len(lines)
        out: List[ChatLine] = []
        for raw in new_lines:
            sender, sep, body = raw.partition(":")
            if sep and body.strip():
                out.append(ChatLine(sender.strip().lstrip("[R4 ]["), body.strip()))
            else:
                out.append(ChatLine("", raw))
        return out

    # -- game -- #
    def in_guild_map(self) -> bool:
        """True bila layar peta klan terlihat (atau template belum tersedia)."""
        candidates = [n for n in ("guild_map", "guild_menu", "bank_panel")
                      if self.matcher.available().get(n)]
        if not candidates:
            return True  # belum dikalibrasi -> jangan blokir
        try:
            with DEVICE_LOCK:
                shot = self.driver.screenshot()
        except DeviceError as exc:
            self._alert("screenshot gagal", str(exc), level="error")
            return False
        for name in candidates:
            m = self.matcher.find(shot, name)
            if m and m.score >= self.min_confidence:
                return True
        self._alert("tidak di layar bank/peta klan", "flow dibatalkan demi keamanan", level="warn")
        return False

    @_with_lock
    def open_bank_panel(self, nick: str) -> None:
        self._run("bank_open_member", {"nick": nick})

    TYPE_LABEL = {"food": "Food", "stone": "Stone", "wood": "Wood", "ore": "Ore", "gold": "Gold"}
    TYPES = ("food", "stone", "wood", "ore", "gold")

    @_with_lock
    def send_rss_to_member(self, nick: str, rss: Dict[str, int]) -> None:
        """Kirim RSS per tipe.

        Prioritas flow: `bank_send_one_type` (satu tipe per putaran, paling
        mudah dikalibrasi) → fallback `bank_send_rss` (semua tipe sekaligus).
        Tipe dengan jumlah 0 dilewati.
        """
        positive = {k: int(v) for k, v in rss.items() if int(v or 0) > 0}
        if not positive:
            raise OpsError("tidak ada RSS yang dikirim (semua 0)")

        one_type = self.flows.get("bank_send_one_type")
        if one_type and one_type.enabled:
            cooldown = float(self.cfg.get("safety.cooldown_between_transfers", 2.0) or 0)
            for idx, key in enumerate(k for k in self.TYPES if k in positive):
                ctx: Dict[str, Any] = {
                    "nick": nick,
                    "type": key,
                    "type_label": self.TYPE_LABEL.get(key, key.title()),
                    "amount": str(positive[key]),
                    "rss": json.dumps({key: positive[key]}),
                    "amount_food": str(positive.get("food", 0)),
                    "amount_stone": str(positive.get("stone", 0)),
                    "amount_wood": str(positive.get("wood", 0)),
                    "amount_ore": str(positive.get("ore", 0)),
                    "amount_gold": str(positive.get("gold", 0)),
                }
                if idx and cooldown:
                    time.sleep(cooldown)
                self._run("bank_send_one_type", ctx)
            return

        ctx = {"nick": nick, "rss": json.dumps(positive)}
        for key in self.TYPES:
            ctx[f"amount_{key}"] = str(int(positive.get(key, 0) or 0))
        self._run("bank_send_rss", ctx)

    @_with_lock
    def run_action(self, action: str, params: Optional[Dict[str, Any]] = None) -> None:
        self._run(action, dict(params or {}))

    def screenshot(self, path: str) -> None:
        self.driver.screenshot().save(self.cfg.resolve_path(path))
