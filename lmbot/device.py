"""Driver perangkat: ADB (MuMu/emulator nyata) dan Mock (uji tanpa emulator).

Driver hanya mengirim perintah yang sama dengan yang dilakukan jari manusia:
screenshot, tap, swipe, ketik teks. Tidak ada hooking/injeksi ke proses game.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .utils import jitter_point

Point = Tuple[int, int]


class DeviceError(Exception):
    pass


@dataclass
class Screen:
    width: int
    height: int
    data: bytes
    fmt: str = "png"

    def save(self, path: str | os.PathLike) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(self.data)


class BaseDriver:
    width: int = 1280
    height: int = 720

    def connect(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def screenshot(self) -> Screen:  # pragma: no cover - interface
        raise NotImplementedError

    def tap(self, x: int, y: int) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        raise NotImplementedError

    def text(self, value: str) -> None:
        raise NotImplementedError

    def tap_fraction(self, fx: float, fy: float) -> None:
        self.tap(int(self.width * fx), int(self.height * fy))

    def close(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# ADB
# --------------------------------------------------------------------------- #
class AdbDriver(BaseDriver):
    def __init__(
        self,
        adb_path: str = "adb",
        serial: str = "127.0.0.1:16384",
        width: int = 1280,
        height: int = 720,
        auto_connect: bool = True,
        jitter: int = 4,
        timeout: int = 20,
        logger=None,
    ) -> None:
        self.adb = adb_path
        self.serial = serial
        self.width = width
        self.height = height
        self.auto_connect = auto_connect
        self.jitter = jitter
        self.timeout = timeout
        self.log = logger
        self.connected = False

    # -- low level -- #
    def _run(self, args: List[str], binary: bool = False, timeout: Optional[int] = None):
        cmd = [self.adb, "-s", self.serial, *args] if self.serial else [self.adb, *args]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout or self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise DeviceError(
                f"adb tidak ditemukan di '{self.adb}'. Set device.adb_path "
                f"ke lokasi platform-tools\\adb.exe"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DeviceError(f"adb timeout: {' '.join(args)}") from exc
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
            raise DeviceError(f"adb gagal ({proc.returncode}): {msg or ' '.join(args)}")
        return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")

    def _info(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    # -- koneksi -- #
    def connect(self) -> None:
        out = self._run(["devices"], timeout=self.timeout)
        if self.serial and self.serial not in out:
            if not self.auto_connect:
                raise DeviceError(f"device {self.serial} tidak terdeteksi (auto_connect=false)")
            self._info(f"menghubungkan ke {self.serial} ...")
            self._run(["connect", self.serial], timeout=self.timeout)
            time.sleep(1.0)
            out = self._run(["devices"], timeout=self.timeout)
            if self.serial not in out:
                raise DeviceError(
                    f"gagal terhubung ke {self.serial}. Pastikan MuMu Player sudah "
                    f"menyalakan ADB (Pengaturan > Lainnya > ADB debugging) "
                    f"dan port-nya sesuai."
                )
        self.connected = True
        size = self._run(["shell", "wm", "size"])
        for token in size.replace("\r", "").split():
            if "x" in token and token[0].isdigit():
                w, h = token.split("x")[:2]
                self.width, self.height = int(w), int(h)
                break
        self._info(f"terhubung ke {self.serial} ({self.width}x{self.height})")

    # -- aksi -- #
    def screenshot(self) -> Screen:
        data = self._run(["exec-out", "screencap", "-p"], binary=True)
        if not data or len(data) < 100:
            raise DeviceError("screenshot kosong — emulator mungkin minimized atau sleep")
        return Screen(self.width, self.height, data)

    def tap(self, x: int, y: int) -> None:
        x, y = jitter_point(x, y, self.jitter)
        self._run(["shell", "input", "tap", str(x), str(y)])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._run(
            ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)]
        )

    def keyevent(self, code: int | str) -> None:
        self._run(["shell", "input", "keyevent", str(code)])

    def text(self, value: str) -> None:
        safe = value.replace(" ", "%s")
        self._run(["shell", "input", "text", safe])

    def current_activity(self) -> str:
        out = self._run(["shell", "dumpsys", "window", "windows"], timeout=25)
        for line in out.splitlines():
            if "mCurrentFocus" in line:
                return line.strip()
        return ""

    def launch(self, package: str, activity: str = "") -> None:
        if activity:
            self._run(["shell", "am", "start", "-n", f"{package}/{activity}"])
        else:
            self._run(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])

    def ensure_portrait_landscape(self, landscape: bool = True) -> None:
        rot = "0" if landscape else "1"
        try:
            self._run(["shell", "settings", "put", "system", "accelerometer_rotation", "0"])
            self._run(["shell", "settings", "put", "system", "user_rotation", rot])
        except DeviceError:
            pass


# --------------------------------------------------------------------------- #
# Mock (unit test / dry-run tanpa emulator)
# --------------------------------------------------------------------------- #
class MockDriver(BaseDriver):
    """Driver palsu: mencatat semua aksi, bisa 'memutar' skrip chat dari file."""

    def __init__(self, width: int = 1280, height: int = 720, script: Optional[List[str]] = None):
        self.width = width
        self.height = height
        self.actions: List[tuple] = []
        self.script = list(script or [])
        self._tick = 0

    def connect(self) -> None:
        self.actions.append(("connect",))

    def screenshot(self) -> Screen:
        self._tick += 1
        self.actions.append(("screenshot", self._tick))
        return Screen(self.width, self.height, b"MOCK", fmt="mock")

    def tap(self, x: int, y: int) -> None:
        self.actions.append(("tap", x, y))

    def swipe(self, x1, y1, x2, y2, duration_ms: int = 300) -> None:
        self.actions.append(("swipe", x1, y1, x2, y2, duration_ms))

    def text(self, value: str) -> None:
        self.actions.append(("text", value))

    def taps(self) -> List[tuple]:
        return [a for a in self.actions if a[0] == "tap"]

    def texts(self) -> List[str]:
        return [a[1] for a in self.actions if a[0] == "text"]


# --------------------------------------------------------------------------- #
# Starter MuMu
# --------------------------------------------------------------------------- #
MUMU_DEFAULT_PATH = r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\MuMuManager.exe"


def start_mumu(
    manager_path: str = MUMU_DEFAULT_PATH,
    instance: int = 0,
    player_path: Optional[str] = None,
) -> str:
    """Nyalakan instance MuMu. Mengembalikan pesan status (dipakai CLI)."""
    if not manager_path or not Path(manager_path).exists():
        raise DeviceError(
            f"MuMuManager tidak ditemukan di '{manager_path}'. "
            f"Set device.mumu_manager ke path MuMuManager.exe yang benar."
        )
    result = subprocess.run(
        [manager_path, "control", "-v", str(instance), "launch"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DeviceError(f"gagal menyalakan MuMu: {result.stderr or result.stdout}")
    return f"MuMu instance {instance} dinyalakan"


def mumu_adb_command(manager_path: str = MUMU_DEFAULT_PATH, instance: int = 0) -> str:
    """Perintah MuMuManager untuk menyalakan ADB (jalankan di PowerShell)."""
    return f'"{manager_path}" adb -v {instance} -cmd "enable" -adb_host 127.0.0.1 -adb_port 16384'


class DeviceSession:
    """Bungkus driver dengan auto-reconnect + ketahanan saat emulator restart.

    Semua aksi driver dilewatkan ke sini; bila DeviceError terjadi, sesi
    mencoba `connect()` ulang dengan backoff sebelum meneruskan error.
    """

    def __init__(self, driver: BaseDriver, retries: int = 2, backoff: float = 2.0, logger=None):
        self.driver = driver
        self.retries = max(0, int(retries))
        self.backoff = float(backoff)
        self.log = logger
        self.reconnects = 0
        self.last_error: Optional[str] = None

    # -- passthrough properti -- #
    @property
    def width(self) -> int:
        return self.driver.width

    @property
    def height(self) -> int:
        return self.driver.height

    def _info(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def _with_retry(self, label: str, fn):
        attempt = 0
        while True:
            try:
                return fn()
            except DeviceError as exc:
                self.last_error = str(exc)
                if attempt >= self.retries:
                    raise
                attempt += 1
                wait = self.backoff * attempt
                self._info(f"[device] {label} gagal ({exc}); reconnect #{attempt} dalam {wait:.1f}s")
                time.sleep(wait)
                try:
                    self.reconnect()
                except DeviceError as rerr:
                    self.last_error = str(rerr)
                    if attempt >= self.retries:
                        raise DeviceError(f"{exc} (reconnect juga gagal: {rerr})") from rerr

    def reconnect(self) -> None:
        self.reconnects += 1
        try:
            self.driver.close()
        except Exception:
            pass
        self.driver.connect()
        self._info(f"[device] tersambung kembali (total reconnect: {self.reconnects})")

    # -- aksi -- #
    def connect(self) -> None:
        self._with_retry("connect", self.driver.connect)

    def screenshot(self) -> Screen:
        return self._with_retry("screenshot", self.driver.screenshot)

    def tap(self, x: int, y: int) -> None:
        self._with_retry("tap", lambda: self.driver.tap(x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._with_retry("swipe", lambda: self.driver.swipe(x1, y1, x2, y2, duration_ms))

    def text(self, value: str) -> None:
        self._with_retry("text", lambda: self.driver.text(value))

    def keyevent(self, code) -> None:
        fn = getattr(self.driver, "keyevent", None)
        if fn:
            self._with_retry("keyevent", lambda: fn(code))

    def tap_fraction(self, fx: float, fy: float) -> None:
        self.tap(int(self.driver.width * fx), int(self.driver.height * fy))

    def close(self) -> None:
        try:
            self.driver.close()
        except Exception:
            pass


def adb_available(adb_path: str = "adb") -> bool:
    if Path(adb_path).exists():
        return True
    return shutil.which(adb_path) is not None


def build_driver(cfg, logger=None) -> BaseDriver:
    dev = cfg.section("device")
    driver = dev.get("driver", "adb")
    if driver == "mock":
        return MockDriver(width=dev["width"], height=dev["height"])
    if driver == "script":
        return MockDriver(width=dev["width"], height=dev["height"])
    return AdbDriver(
        adb_path=dev.get("adb_path", "adb"),
        serial=dev.get("serial", "127.0.0.1:16384"),
        width=dev["width"],
        height=dev["height"],
        auto_connect=dev.get("auto_connect", True),
        jitter=cfg.get("flows.tap_jitter", 4),
        timeout=dev.get("screenshot_timeout", 20),
        logger=logger,
    )
