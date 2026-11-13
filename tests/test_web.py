"""Uji dashboard & webhook memakai Bot + MockOps (tanpa emulator)."""
from __future__ import annotations

import json
import urllib.request

import pytest

from lmbot.bot import Bot
from lmbot.config import load_config
from lmbot.ops import MockOps


@pytest.fixture()
def dashboard(cfg, tmp_path):
    from lmbot.web import start_dashboard

    cfg.data["bank"]["path"] = str(tmp_path / "bank.json")
    ops = MockOps()
    bot = Bot(cfg, ops)
    bot.bank.roster.set_member("lady_ayu", "R5")
    bot.bank.credit("lady_ayu", {"food": 42_000_000})
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
        data=json.dumps({"text": "!top", "sender": "lady_ayu"}).encode(),
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
        ok = urllib.request.urlopen(base + "/?token=s3cret")
        assert b"Guild Bank" in ok.read()
    finally:
        srv.shutdown()
