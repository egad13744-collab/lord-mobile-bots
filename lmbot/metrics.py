"""Penghitung metrik ringan + ekspor format Prometheus.

Tanpa dependensi eksternal: cukup dict + lock. Dipakai dashboard (`/metrics`)
dan `:stats` di REPL. Semua metrik bersifat monoton naik kecuali gauge.
"""
from __future__ import annotations

import threading
import time
from typing import Dict


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self.counters: Dict[str, float] = {}
        self.commands: Dict[str, int] = {}
        self.command_errors: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}

    # -- mutasi -- #
    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self.counters[name] = self.counters.get(name, 0.0) + value

    def observe_command(self, name: str, ok: bool) -> None:
        with self._lock:
            self.commands[name] = self.commands.get(name, 0) + 1
            if not ok:
                self.command_errors[name] = self.command_errors.get(name, 0) + 1
            self.counters["lmbot_commands_total"] = self.counters.get("lmbot_commands_total", 0) + 1

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self.gauges[name] = float(value)

    # -- baca -- #
    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "uptime_seconds": round(time.time() - self.started, 1),
                "counters": dict(self.counters),
                "commands": dict(self.commands),
                "errors": dict(self.command_errors),
                "gauges": dict(self.gauges),
            }

    def top_commands(self, limit: int = 5):
        with self._lock:
            rows = sorted(self.commands.items(), key=lambda kv: kv[1], reverse=True)
        return rows[:limit]

    def render_prometheus(self) -> str:
        """Format teks yang bisa langsung di-scrape Prometheus."""
        snap = self.snapshot()
        lines = [
            "# HELP lmbot_uptime_seconds Lama bot berjalan.",
            "# TYPE lmbot_uptime_seconds gauge",
            f"lmbot_uptime_seconds {snap['uptime_seconds']}",
        ]
        for name, val in sorted(snap["counters"].items()):  # type: ignore[union-attr]
            if name.startswith("lmbot_"):
                lines += [f"# TYPE {name} counter", f"{name} {val}"]
        lines.append("# TYPE lmbot_command_total counter")
        def label(value: str) -> str:
            return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "")
        for name, val in sorted(snap["commands"].items()):  # type: ignore[union-attr]
            lines.append(f'lmbot_command_total{{command="{label(name)}"}} {val}')
        lines.append("# TYPE lmbot_command_error_total counter")
        for name, val in sorted(snap["errors"].items()):  # type: ignore[union-attr]
            lines.append(f'lmbot_command_error_total{{command="{label(name)}"}} {val}')
        for name, val in sorted(snap["gauges"].items()):  # type: ignore[union-attr]
            lines += [f"# TYPE {name} gauge", f"{name} {val}"]
        return "\n".join(lines) + "\n"


# Metrik global proses (dipakai Bot kalau tidak diberi instance sendiri).
GLOBAL = Metrics()
