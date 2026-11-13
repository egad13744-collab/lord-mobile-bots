"""Sumber perintah: terminal, file (tail), HTTP webhook, dan chat in-game.

Kenapa banyak sumber? Karena fitur tetap bisa dipakai walau OCR chat game
belum dikonfigurasi. Alur paling umum di RDP: buka terminal -> `lmbot serve`
lalu ketik perintah langsung, atau kirim lewat webhook dari HP.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
class _Handler(BaseHTTPRequestHandler):
    bot = None  # diisi saat start
    token = ""
    inbox: "queue.Queue[tuple[str, str]]" = queue.Queue()

    def log_message(self, fmt, *args):  # senyap
        pass

    def _auth(self) -> bool:
        if not self.token:
            return True
        hdr = self.headers.get("X-Bot-Token", "")
        return hdr == self.token

    def do_GET(self):  # health
        body = json.dumps({"ok": True, "uptime": self.bot.uptime() if self.bot else ""}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._auth():
            self.send_response(401)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        text = str(payload.get("text") or payload.get("message") or "").strip()
        sender = str(payload.get("sender") or "").strip()
        if not text:
            self.send_response(400)
            self.end_headers()
            return
        reply = self.bot.handle_line(text, sender or None) if self.bot else None
        body = json.dumps(
            {"ok": bool(reply and reply.ok), "reply": reply.message if reply else ""},
            ensure_ascii=False,
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_http(bot, host: str = "0.0.0.0", port: int = 8080, token: str = "") -> ThreadingHTTPServer:
    handler = type("_BotHandler", (_Handler,), {"bot": bot, "token": token})
    srv = ThreadingHTTPServer((host, port), handler)
    t = threading.Thread(target=srv.serve_forever, name="lmbot-http", daemon=True)
    t.start()
    return srv


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
