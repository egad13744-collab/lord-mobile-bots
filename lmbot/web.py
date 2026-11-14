"""Dashboard status ringan (opsional) + endpoint webhook perintah.

Satu server, dua fungsi:
  GET  /            -> halaman HTML status (saldo, transaksi, alert, template)
  GET  /api/status  -> JSON status
  POST /            -> kirim perintah ({"text": "!bal", "sender": "arken_ega"})

Aman untuk LAN: token opsional (header X-Bot-Token atau ?token=).
"""
from __future__ import annotations

import html
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .imaging import EXPECTED_TEMPLATES, list_templates
from .utils import fmt_rss, human


def _page(bot) -> str:
    bank = bot.bank
    st = bank.stats()
    labels = {"food": "Food", "stone": "Stone", "wood": "Wood", "ore": "Ore", "gold": "Gold"}
    total = fmt_rss(bank.bank_total(), labels)
    rows = "".join(
        f"<tr><td>{html.escape(str(t.get('time','')))}</td><td>{html.escape(str(t.get('kind','')))}</td>"
        f"<td>{html.escape(str(t.get('nick','')))}</td>"
        f"<td>{html.escape(', '.join(f'{k}:{human(v)}' for k, v in (t.get('rss') or {}).items() if v))}</td></tr>"
        for t in reversed(bank.recent(15))
    ) or "<tr><td colspan=4><i>belum ada transaksi</i></td></tr>"

    top = "".join(
        f"<li>{html.escape(nick)} — {human(val)}</li>" for nick, val in bank.leaderboard("food", 5)
    ) or "<li><i>kosong</i></li>"

    tstatus = list_templates(bot.cfg.resolve_path(bot.cfg.get("templates.dir", "assets/templates")))
    tpl_rows = "".join(
        f"<tr><td>{name}</td><td>{'✔' if tstatus[name] else '✘'}</td>"
        f"<td class=dim>{html.escape(desc)}</td></tr>"
        for name, desc in EXPECTED_TEMPLATES.items()
    )
    alerts = getattr(bot.ops, "alerts", None)
    arows = "".join(
        f"<li>[{html.escape(str(a.get('level')))}] {html.escape(str(a.get('time')))} "
        f"{html.escape(str(a.get('title')))} — {html.escape(str(a.get('detail')))[:120]}</li>"
        for a in (alerts.recent(8) if alerts else [])
    ) or "<li><i>tidak ada peringatan</i></li>"

    frozen = bank.freeze_remaining()
    banner = (
        f"<div class=warn>⏸️ Bank dijeda {frozen} detik</div>" if frozen else
        "<div class=ok>▶️ Bank aktif</div>"
    )

    return f"""<!doctype html>
<html lang=id><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>LMBot — Guild Bank</title>
<style>
 body{{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}}
 header{{padding:18px 22px;background:#171a21;border-bottom:1px solid #262b36}}
 h1{{margin:0;font-size:18px;letter-spacing:.3px}}
 main{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));padding:18px}}
 section{{background:#171a21;border:1px solid #262b36;border-radius:10px;padding:14px 16px}}
 h2{{font-size:13px;text-transform:uppercase;color:#8b93a7;margin:0 0 10px;letter-spacing:.6px}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 td,th{{padding:5px 6px;border-bottom:1px solid #20242e;text-align:left;vertical-align:top}}
 .dim{{color:#7f879a;font-size:12px}} .ok{{color:#4ade80}} .warn{{color:#fbbf24}}
 ul{{margin:0;padding-left:18px;font-size:13px}}
 code{{background:#0b0d11;padding:1px 5px;border-radius:4px}}
</style></head><body>
<header><h1>LMBot — Guild Bank Lord Mobile</h1>
<div class=dim>Dibuat oleh Egandika</div>
<div class=dim>uptime {bot.uptime()} · {html.escape(bot.summary())}</div></header>
<main>
<section><h2>Status bank</h2>{banner}
<p><b>Total tabungan:</b> {html.escape(total)}<br>
<b>Member:</b> {st['members']} · <b>Whitelist:</b> {st['whitelist']} ·
<b>Blacklist:</b> {st['blacklist']} · <b>Transaksi:</b> {st['transactions']}</p>
<h2 style="margin-top:14px">Top 5 Food</h2><ul>{top}</ul></section>
<section><h2>Transaksi terakhir</h2>
<table><tr><th>Waktu</th><th>Jenis</th><th>Nick</th><th>RSS</th></tr>{rows}</table></section>
<section><h2>Template UI</h2>
<table><tr><th>Nama</th><th>Siap</th><th>Fungsi</th></tr>{tpl_rows}</table></section>
<section><h2>Peringatan</h2><ul>{arows}</ul>
<p class=dim>Kirim perintah: <code>POST / {"{"}"text":"!bal","sender":"arken_ega"{"}"}</code></p></section>
</main>
<footer style="padding:10px 22px 22px;color:#7f879a;font-size:12px">
 LMBot · Dibuat oleh Egandika
</footer></body></html>"""


class _DashboardHandler(BaseHTTPRequestHandler):
    bot = None
    token = ""
    roles = None
    access_path = None
    rate_limit = 60
    rate_window = 60
    _hits = defaultdict(deque)
    _hits_lock = threading.Lock()
    _pending = {}
    _pending_lock = threading.Lock()

    def log_message(self, fmt, *args):
        pass

    def _client_ip(self) -> str:
        # Jangan percaya X-Forwarded-For kecuali reverse proxy dikonfigurasi.
        return str(self.client_address[0])

    def _rate_ok(self) -> bool:
        now = time.monotonic()
        ip = self._client_ip()
        with self._hits_lock:
            q = self._hits[ip]
            while q and now - q[0] > self.rate_window:
                q.popleft()
            if len(q) >= self.rate_limit:
                return False
            q.append(now)
            return True

    def _role(self):
        supplied = self.headers.get("X-Bot-Token", "")
        if not supplied:
            # kompatibilitas lama, tapi jangan gunakan query token pada deployment baru
            supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if self.roles:
            for role, token in self.roles.items():
                if token and secrets.compare_digest(str(token), supplied):
                    return str(role).lower()
        elif self.token and secrets.compare_digest(self.token, supplied):
            return "owner"
        elif not self.token and self.client_address[0] in {"127.0.0.1", "::1"}:
            return "owner"  # mode tanpa token hanya loopback; konfigurasi token untuk LAN
        return None

    def _allowed(self, minimum="viewer") -> bool:
        role = self._role()
        levels = {"viewer": 0, "admin": 1, "owner": 2}
        if role is None or levels.get(role, -1) < levels.get(minimum, 0):
            code = 401 if role is None else 403
            self._access("auth-failed", code)
            self._send(code,
                       json.dumps({"ok": False, "error": "token/role"}).encode(),
                       "application/json; charset=utf-8")
            return False
        if not self._rate_ok():
            self._access("rate-limit", 429)
            self._send(429, b'{"ok":false,"error":"rate limit"}', "application/json")
            return False
        return True

    def _access(self, action: str, status: int, detail="") -> None:
        p = self.access_path
        if not p:
            return
        try:
            p = Path(p)
            p.parent.mkdir(parents=True, exist_ok=True)
            row = {"ts": time.time(), "ip": self._client_ip(), "method": self.command,
                   "path": self.path.split("?", 1)[0], "action": action,
                   "status": status, "detail": str(detail)[:180]}
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/metrics":
            # Prometheus endpoint protected by viewer-role token.
            if not self._allowed("viewer"):
                return
            body = self.bot.metrics.render_prometheus().encode()
            self._send(200, body, "text/plain; version=0.0.4; charset=utf-8")
            self._access("metrics", 200)
            return
        if path == "/api/health":
            # health endpoint only discloses liveness, still rate-limited
            if not self._allowed("viewer"):
                return
            self._send(200, json.dumps({"ok": True, "uptime": self.bot.uptime(),
                                      "profile": self.bot.cfg.get("bot.profile", "default")}).encode(),
                       "application/json; charset=utf-8")
            self._access("health", 200)
            return
        if not self._allowed("viewer"):
            return
        if path == "/api/status":
            st = self.bot.bank.stats()
            st.update(uptime=self.bot.uptime(), stats=self.bot.stats,
                      metrics=self.bot.metrics.snapshot(),
                      queue=self.bot.queue.stats() if self.bot.queue else {},
                      alerts=(getattr(self.bot.ops, "alerts", None).recent(5)
                              if getattr(self.bot.ops, "alerts", None) else []))
            body = json.dumps(st, default=str).encode()
            self._send(200, body, "application/json; charset=utf-8")
            self._access("status", 200)
            return
        if path != "/":
            self._send(404, b'{"ok":false,"error":"not found"}', "application/json")
            return
        self._send(200, _page(self.bot).encode(), "text/html; charset=utf-8")
        self._access("dashboard", 200)

    def _payload(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 16_384:
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _is_risky(self, text: str) -> bool:
        try:
            from .parser import parse
            normalized = self.bot.custom.resolve_alias(text) if getattr(self.bot, "custom", None) else text
            return bool(parse(normalized).spec.risky)
        except Exception:
            return False

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/", "/api/confirm"):
            self._send(404, b'{"ok":false,"error":"not found"}', "application/json")
            return
        if not self._allowed("admin"):
            return
        payload = self._payload()
        if payload is None:
            self._send(400, b'{"ok":false,"error":"JSON tidak valid / terlalu besar"}', "application/json")
            return
        text = str(payload.get("text") or payload.get("message") or "").strip()
        sender = str(payload.get("sender") or "").strip()
        if not text:
            self._send(400, b'{"ok":false,"error":"text kosong"}', "application/json")
            return
        # Role token mengikat identitas pengirim. Admin API tidak boleh
        # menyamar sebagai owner lewat field sender di JSON.
        role = self._role()
        role_tokens_active = bool(self.roles)
        if role_tokens_active:
            identities = self.bot.cfg.get("web.identities", {}) or {}
            expected = identities.get(role) or (
                self.bot.cfg.get("bot.owner_nick", "") if role == "owner" else ""
            )
            if not expected:
                self._send(403, b'{"ok":false,"error":"web.identities belum dikonfigurasi"}', "application/json")
                self._access("identity-missing", 403)
                return
            from .utils import normalize_nick
            if sender and normalize_nick(sender) != normalize_nick(str(expected)):
                self._send(403, b'{"ok":false,"error":"sender tidak cocok dengan identitas token"}', "application/json")
                self._access("identity-mismatch", 403)
                return
            sender = str(expected)

        if self._is_risky(text) and path != "/api/confirm":
            nonce = secrets.token_urlsafe(20)
            with type(self)._pending_lock:
                now = time.monotonic()
                type(self)._pending = {k: v for k, v in type(self)._pending.items()
                                       if now - v["ts"] < 120}
                type(self)._pending[nonce] = {"ts": now, "text": text, "sender": sender,
                                              "ip": self._client_ip(), "role": role}
            body = json.dumps({"ok": False, "confirmation_required": True, "nonce": nonce,
                               "message": "Perintah berisiko perlu konfirmasi eksplisit; POST /api/confirm dengan nonce dan text yang sama."}).encode()
            self._send(202, body, "application/json; charset=utf-8")
            self._access("confirm-required", 202, text)
            return
        if path == "/api/confirm":
            nonce = str(payload.get("nonce") or "")
            with type(self)._pending_lock:
                pending = type(self)._pending.pop(nonce, None)
            if (not pending or time.monotonic() - pending["ts"] > 120 or
                pending["ip"] != self._client_ip() or pending["text"] != text or
                pending["sender"] != sender or pending.get("role") != role):
                self._send(409, b'{"ok":false,"error":"konfirmasi tidak valid/kedaluwarsa"}', "application/json")
                self._access("confirm-rejected", 409)
                return
        execute_text = text
        if path == "/api/confirm":
            try:
                from .parser import parse
                command = parse(text, sender)
                if any(token.strip("<>?") == "confirm" for token in command.spec.pattern.split()):
                    execute_text = text.rstrip() + " confirm"
            except Exception:
                pass
        reply = self.bot.handle_line(execute_text, sender or None)
        body = json.dumps({"ok": reply.ok, "reply": reply.message}, ensure_ascii=False).encode()
        self._send(200, body, "application/json; charset=utf-8")
        self._access("command", 200 if reply.ok else 400, text)


def start_dashboard(bot, host: str = "0.0.0.0", port: int = 8081, token: str = "") -> ThreadingHTTPServer:
    web_cfg = bot.cfg.section("web")
    raw_roles = web_cfg.get("roles") or {}
    roles = {str(k).lower(): str(v) for k, v in raw_roles.items()
             if str(k).lower() in {"owner", "admin", "viewer"} and v}
    if not roles and token:
        roles = {}
    access_path = bot.cfg.resolve_path(web_cfg.get("access_log", "logs/access.jsonl"))
    limit = int(web_cfg.get("rate_limit_per_minute", 60) or 60)
    handler = type("_DashHandler", (_DashboardHandler,), {
        "bot": bot, "token": token, "roles": roles,
        "access_path": str(access_path), "rate_limit": max(1, limit),
    })
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="lmbot-dashboard", daemon=True).start()
    return srv


def dashboard_port(args) -> Optional[int]:
    return getattr(args, "web_port", 0) or None
