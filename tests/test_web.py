"""Uji dashboard & webhook memakai Bot + MockOps (tanpa emulator)."""
from __future__ import annotations

import json
import urllib.request

import pytest

from lmbot.bot import Bot
from lmbot.ops import MockOps


@pytest.fixture()
def dashboard(cfg, tmp_path):
    from lmbot.web import start_dashboard

    cfg.data["bank"]["path"] = str(tmp_path / "bank.json")
    ops = MockOps()
    bot = Bot(cfg, ops)
    bot.bank.roster.set_member("arken_ega", "R5")
    bot.bank.credit("arken_ega", {"food": 42_000_000})
    srv = start_dashboard(bot, host="127.0.0.1", port=0, token="")
    port = srv.server_address[1]
    yield bot, f"http://127.0.0.1:{port}"
    srv.shutdown()


def test_dashboard_html(dashboard):
    _bot, base = dashboard
    html = urllib.request.urlopen(base + "/").read().decode()
    assert "Guild Bank" in html
    assert "Total tabungan" in html
    assert "send_button" in html  # tabel template
    assert "42M" in html or "42.0M" in html


def test_dashboard_status_json(dashboard):
    _bot, base = dashboard
    data = json.loads(urllib.request.urlopen(base + "/api/status").read())
    assert data["members"] >= 1
    assert "uptime" in data


def test_dashboard_post_command(dashboard):
    _bot, base = dashboard
    req = urllib.request.Request(
        base + "/",
        data=json.dumps({"text": "!top", "sender": "arken_ega"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(req).read())
    assert body["ok"] and "Food" in body["reply"]


def test_dashboard_rejects_unknown_sender(dashboard):
    _bot, base = dashboard
    req = urllib.request.Request(
        base + "/",
        data=json.dumps({"text": "!bal", "sender": "orang_asing"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(req).read())
    assert body["ok"] is False and "whitelist" in body["reply"]


def test_dashboard_token_required(cfg, tmp_path):
    from lmbot.web import start_dashboard

    cfg.data["bank"]["path"] = str(tmp_path / "b.json")
    bot = Bot(cfg, MockOps())
    srv = start_dashboard(bot, host="127.0.0.1", port=0, token="s3cret")
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base + "/")
        assert exc.value.code == 401
        req = urllib.request.Request(base + "/", headers={"X-Bot-Token": "s3cret"})
        ok = urllib.request.urlopen(req)
        assert b"Guild Bank" in ok.read()
        # Token pada URL tidak lagi diterima (dapat bocor ke log/proxy).
        with pytest.raises(urllib.error.HTTPError) as query_exc:
            urllib.request.urlopen(base + "/?token=s3cret")
        assert query_exc.value.code == 401
    finally:
        srv.shutdown()


def test_dashboard_credit_footer(dashboard):
    _bot, base = dashboard
    html = urllib.request.urlopen(base + "/").read().decode()
    assert "Dibuat oleh Egandika" in html


def test_metrics_and_health_endpoints(dashboard):
    bot, base = dashboard
    bot.handle_line("!top", "arken_ega")
    metrics = urllib.request.urlopen(base + "/metrics").read().decode()
    assert "lmbot_commands_total" in metrics
    health = json.loads(urllib.request.urlopen(base + "/api/health").read())
    assert health["ok"] is True


def test_risky_command_requires_confirm(dashboard):
    bot, base = dashboard
    bot.bank.roster.set_member("officer", "R4")
    token = "secret"
    # Server test fixture dibuat tanpa token, jadi jalankan server ber-token.
    from lmbot.web import start_dashboard
    srv = start_dashboard(bot, host="127.0.0.1", port=0, token=token)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def post(path, data):
            req = urllib.request.Request(base + path,
                data=json.dumps(data).encode(),
                headers={"X-Bot-Token": token, "Content-Type": "application/json"})
            return urllib.request.urlopen(req)
        body = json.loads(post("/", {"text": "!relocate 123 456", "sender": "officer"}).read())
        assert body["confirmation_required"] is True
        confirmed = json.loads(post("/api/confirm", {
            "text": "!relocate 123 456", "sender": "officer", "nonce": body["nonce"]
        }).read())
        assert confirmed["ok"] is True
        assert "relocate" in bot.ops.actions()
    finally:
        srv.shutdown()


def test_role_tokens_bind_sender_identity(cfg, tmp_path):
    from lmbot.web import start_dashboard
    cfg.data["bank"]["path"] = str(tmp_path / "role-bank.json")
    cfg.data["web"]["roles"] = {"admin": "admin-secret", "viewer": "viewer-secret"}
    cfg.data["web"]["identities"] = {"admin": "officer"}
    bot = Bot(cfg, MockOps())
    bot.bank.roster.set_member("officer", "R4")
    srv = start_dashboard(bot, host="127.0.0.1", port=0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        viewer = urllib.request.Request(base + "/api/status", headers={"X-Bot-Token": "viewer-secret"})
        assert urllib.request.urlopen(viewer).status == 200
        spoof = urllib.request.Request(base + "/", data=json.dumps({
            "text": "!top", "sender": "arken_ega"
        }).encode(), headers={"X-Bot-Token": "admin-secret", "Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(spoof)
        assert err.value.code == 403
        valid = urllib.request.Request(base + "/", data=json.dumps({
            "text": "!top", "sender": "officer"
        }).encode(), headers={"X-Bot-Token": "admin-secret", "Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(valid).read())["ok"] is True
    finally:
        srv.shutdown()
