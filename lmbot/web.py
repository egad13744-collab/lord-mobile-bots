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

    def log_message(self, fmt, *args):
        pass

    def _auth(self) -> bool:
        if not self.token:
            return True
        if self.headers.get("X-Bot-Token") == self.token:
            return True
        if f"token={self.token}" in (self.path or ""):
            return True
        return False

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if not self._auth():
            self._send(401, b'{"ok":false,"error":"token"}', "application/json")
            return
        if self.path.startswith("/api/status"):
            st = self.bot.bank.stats()
            st.update(
                uptime=self.bot.uptime(),
                stats=self.bot.stats,
                alerts=(getattr(self.bot.ops, "alerts", None).recent(5)
                        if getattr(self.bot.ops, "alerts", None) else []),
            )
            self._send(200, json.dumps(st, default=str).encode(), "application/json; charset=utf-8")
            return
        self._send(200, _page(self.bot).encode(), "text/html; charset=utf-8")

    def do_POST(self):
        if not self._auth():
            self._send(401, b'{"ok":false,"error":"token"}', "application/json")
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
            self._send(400, b'{"ok":false,"error":"text kosong"}', "application/json")
            return
        reply = self.bot.handle_line(text, sender or None)
        body = json.dumps({"ok": reply.ok, "reply": reply.message}, ensure_ascii=False).encode()
        self._send(200, body, "application/json; charset=utf-8")


def start_dashboard(bot, host: str = "0.0.0.0", port: int = 8081, token: str = "") -> ThreadingHTTPServer:
    handler = type("_DashHandler", (_DashboardHandler,), {"bot": bot, "token": token})
    srv = ThreadingHTTPServer((host, port), handler)
    import threading

    threading.Thread(target=srv.serve_forever, name="lmbot-dashboard", daemon=True).start()
    return srv


def dashboard_port(args) -> Optional[int]:
    return getattr(args, "web_port", 0) or None
