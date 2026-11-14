"""Penjaga kesehatan bot (watchdog) & self-healing.

Bot premium umumnya punya "auto-recover": kalau emulator mati, ADB putus, atau
flow gagal berulang, bot menyambung ulang sendiri dan mengirim notifikasi.
Modul ini menyediakan:

* `Watchdog` — thread yang memeriksa driver tiap N detik: cek screenshot,
  reconnect bila gagal, alert setelah K kegagalan berturut, dan memicu
  `recover_hook` (mis. tutup popup nyasar).
* `heal_config` — melengkapi folder/state/config yang hilang (dipakai
  `code.py doctor --fix`).
* `disk_guard` — peringatan bila folder log/ state membengkak.
"""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional


class Watchdog:
    def __init__(
        self,
        driver,
        interval: float = 30.0,
        fail_threshold: int = 3,
        alerts=None,
        logger=None,
        recover_hook: Optional[Callable[[], None]] = None,
    ):
        self.driver = driver
        self.interval = interval
        self.fail_threshold = fail_threshold
        self.alerts = alerts
        self.log = logger
        self.recover_hook = recover_hook
        self.failures = 0
        self.checks = 0
        self.last_ok = time.time()
        self.reconnects = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- satu siklus (bisa dipanggil manual untuk test) -- #
    def check(self) -> bool:
        self.checks += 1
        try:
            was_unhealthy = self.failures > 0
            self.driver.screenshot()
            self.failures = 0
            self.last_ok = time.time()
            if was_unhealthy and self.recover_hook:
                try:
                    self.recover_hook()
                except Exception as exc:  # best-effort popup recovery
                    if self.log:
                        self.log(f"[watchdog] recover hook gagal: {exc}")
            return True
        except Exception as exc:  # DeviceError/OpsError apa pun
            self.failures += 1
            if self.log:
                self.log(f"[watchdog] gagal {self.failures}x: {exc}")
            if self.failures == self.fail_threshold:
                self._notify("warn", "watchdog: perangkat tidak merespons", str(exc))
                self._reconnect()
            elif self.failures > self.fail_threshold and self.failures % self.fail_threshold == 0:
                self._reconnect()
            return False

    def _reconnect(self) -> None:
        self.reconnects += 1
        try:
            connect = getattr(self.driver, "connect", None)
            if callable(connect):
                connect()
                if self.log:
                    self.log(f"[watchdog] reconnect #{self.reconnects}")
        except Exception as exc:  # pragma: no cover - bergantung perangkat
            if self.log:
                self.log(f"[watchdog] reconnect gagal: {exc}")
            self._notify("error", "watchdog: reconnect gagal", str(exc))

    def _notify(self, level: str, title: str, detail: str) -> None:
        if self.alerts:
            self.alerts.send(level, title, detail)

    # -- thread -- #
    def start(self) -> "Watchdog":
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(target=self._loop, name="lmbot-watchdog", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.check()
            self._stop.wait(self.interval)

    def status(self) -> Dict[str, object]:
        return {
            "checks": self.checks,
            "failures": self.failures,
            "reconnects": self.reconnects,
            "last_ok": self.last_ok,
            "healthy": self.failures < self.fail_threshold,
        }


# --------------------------------------------------------------------------- #
# Self-healing konfigurasi & folder
# --------------------------------------------------------------------------- #
def heal_config(cfg) -> List[str]:
    """Buat folder/file yang hilang dan rapikan config bernilai contoh.

    Kembalikan daftar tindakan yang dilakukan (untuk ditampilkan `doctor --fix`).
    """
    actions: List[str] = []
    root = cfg.root
    for rel in ("logs", "state", "assets/templates", "assets/ocr", "config/flows"):
        path = cfg.resolve_path(rel)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            actions.append(f"buat folder {rel}/")

    # bank state
    bank_path = cfg.resolve_path(cfg.get("bank.path", "state/bank.json"))
    if not bank_path.parent.exists():
        bank_path.parent.mkdir(parents=True, exist_ok=True)
        actions.append(f"buat folder {bank_path.parent.relative_to(root) if root in bank_path.parents else bank_path.parent}")

    # config aman
    if cfg.get("device.driver") == "adb" and not str(cfg.get("device.adb_path") or "").strip():
        cfg.data["device"]["adb_path"] = "adb"
        actions.append("set device.adb_path = adb")

    if float(cfg.get("alerts.throttle_seconds", 30) or 0) < 5:
        cfg.data["alerts"]["throttle_seconds"] = 30
        actions.append("set alerts.throttle_seconds = 30 (hindari spam)")

    if int(cfg.get("bot.max_commands_per_minute", 20) or 0) > 120:
        cfg.data["bot"]["max_commands_per_minute"] = 60
        actions.append("batasi bot.max_commands_per_minute = 60")

    flows_dir = cfg.resolve_path(cfg.get("flows.dir", "config/flows"))
    if flows_dir.exists() and not list(flows_dir.glob("*.yaml")):
        actions.append("PERINGATAN: config/flows/ kosong — salin ulang dari repo")

    return actions


def disk_guard(cfg, warn_mb: int = 200) -> List[str]:
    """Laporkan file yang membengkak (log/state) supaya bot tidak memenuhi disk."""
    out: List[str] = []
    for rel in ("logs", "state"):
        d = cfg.resolve_path(rel)
        if not d.exists():
            continue
        total = sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
        if total > warn_mb * 1024 * 1024:
            out.append(f"{rel}/ sudah {total / 1024 / 1024:.0f} MB (batas {warn_mb} MB) — rotasi/arsipkan")
    return out


def rotate_log(path: str | Path, max_mb: float = 20.0, keep: int = 5) -> Optional[Path]:
    """Arsipkan file log bila ukurannya melebihi max_mb."""
    p = Path(path)
    if not p.exists() or p.stat().st_size < max_mb * 1024 * 1024:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = p.with_name(f"{p.stem}-{stamp}{p.suffix}")
    shutil.move(str(p), str(dest))
    for old in sorted(p.parent.glob(f"{p.stem}-*{p.suffix}"))[:-keep]:
        try:
            old.unlink()
        except OSError:  # pragma: no cover
            pass
    return dest
