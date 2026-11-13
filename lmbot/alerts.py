"""Kanal peringatan: file log + webhook keluar opsional.

Dipakai saat aksi gagal, device putus, atau OCR error. Admin bisa memantau
dari HP tanpa membuka RDP.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

LEVELS = ("info", "warn", "error")


class AlertSink:
    def __init__(self, cfg, logger=None, path: Optional[str] = None):
        self.cfg = cfg
        self.log = logger
        self.path = Path(path) if path else cfg.resolve_path(
            cfg.get("alerts.file", "logs/alerts.jsonl")
        )
        self.webhook = str(cfg.get("alerts.webhook_url") or "").strip()
        self.min_level = str(cfg.get("alerts.min_level", "warn")).lower()
        self._lock = threading.Lock()
        self._last: Dict[str, float] = {}
        self.throttle = float(cfg.get("alerts.throttle_seconds", 30) or 0)

    def _allowed(self, level: str) -> bool:
        try:
            return LEVELS.index(level) >= LEVELS.index(self.min_level)
        except ValueError:
            return True

    def send(self, level: str, title: str, detail: str = "", **extra: Any) -> None:
        if not self._allowed(level):
            return
        key = f"{level}:{title}"
        now = time.time()
        with self._lock:
            if self.throttle and now - self._last.get(key, 0) < self.throttle:
                return
            self._last[key] = now

        record = {
            "ts": now,
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "level": level,
            "title": title,
            "detail": detail,
            **extra,
        }
        if self.log:
            getattr(self.log, "error" if level == "error" else "warning", self.log.info)(
                f"[alert] {title}: {detail}"
            )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
        if self.webhook:
            self._post(record)

    def _post(self, record: Dict[str, Any]) -> None:
        body = json.dumps(
            {"text": f"[LMBot][{record['level']}] {record['title']}: {record['detail']}"},
            ensure_ascii=False,
        ).encode()
        req = urllib.request.Request(
            self.webhook, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req, timeout=5).close()
        except (urllib.error.URLError, OSError) as exc:  # pragma: no cover - jaringan
            if self.log:
                self.log.warning(f"gagal kirim webhook alert: {exc}")

    def recent(self, limit: int = 20) -> list:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows
