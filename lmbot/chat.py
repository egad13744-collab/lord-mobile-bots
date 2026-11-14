"""Sumber perintah: terminal, file (tail), HTTP webhook, dan chat in-game.

Kenapa banyak sumber? Karena fitur tetap bisa dipakai walau OCR chat game
belum dikonfigurasi. Alur paling umum di RDP: buka terminal -> `lmbot serve`
lalu ketik perintah langsung, atau kirim lewat webhook dari HP.
"""
from __future__ import annotations

import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, List

from .ops import ChatLine, GameOps, OpsError


# --------------------------------------------------------------------------- #
# Terminal (stdin)
# --------------------------------------------------------------------------- #
def terminal_source(prompt: str = "lmbot> ") -> Iterable[tuple[str, str]]:
    while True:
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            return
        yield line, ""


# --------------------------------------------------------------------------- #
# File (tail -f sederhana) — cocok untuk skrip eksternal / AutoHotkey
# --------------------------------------------------------------------------- #
def tail_source(path: str | Path, poll: float = 0.5) -> Iterable[tuple[str, str]]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch(exist_ok=True)
    with p.open("r", encoding="utf-8") as fh:
        fh.seek(0, 2)
        while True:
            line = fh.readline()
            if not line:
                time.sleep(poll)
                continue
            line = line.rstrip("\n")
            if not line.strip():
                continue
            sender = ""
            if "|" in line:
                sender, _, line = line.partition("|")
                sender = sender.strip()
            yield line.strip(), sender


# --------------------------------------------------------------------------- #
# HTTP webhook
# --------------------------------------------------------------------------- #
def start_http(bot, host: str = "0.0.0.0", port: int = 8080, token: str = "") -> ThreadingHTTPServer:
    """Webhook lama memakai lapisan dashboard yang hardened.

    Endpoint yang tersedia: POST / (perintah), POST /api/confirm (aksi berisiko),
    GET /api/health, GET /api/status, dan GET /metrics. Auth/rate-limit/audit
    tidak diduplikasi agar dua server tidak memiliki kebijakan yang berbeda.
    """
    from .web import start_dashboard
    return start_dashboard(bot, host=host, port=port, token=token)


# --------------------------------------------------------------------------- #
# Chat in-game (butuh OCR)
# --------------------------------------------------------------------------- #
def chat_source(ops: GameOps, poll: float = 3.0, logger=None) -> Iterable[tuple[str, str]]:
    """Baca chat in-game berulang. `ops.read_chat` melempar OpsError bila OCR
    belum siap — pemanggil (CLI) akan menjelaskan ke user."""
    seen: set[tuple[str, str]] = set()
    while True:
        try:
            lines: List[ChatLine] = ops.read_chat()
        except OpsError:
            raise
        for line in lines:
            key = (line.sender, line.text)
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > 500:
                seen = set(list(seen)[-200:])
            yield line.text, line.sender
        time.sleep(poll)
