"""Fixture bersama untuk semua test (tanpa emulator)."""
from __future__ import annotations

from pathlib import Path

import pytest

from lmbot.config import load_config
from lmbot.ops import MockOps
from lmbot.state import BankStore

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _root_cwd():
    """Bot memakai path relatif ke root repo; pastikan konsisten."""
    import os

    os.chdir(ROOT)


@pytest.fixture()
def cfg(tmp_path):
    c = load_config(ROOT / "config" / "settings.yaml")
    c.data["device"]["driver"] = "mock"
    c.data["bank"]["path"] = str(tmp_path / "bank.json")
    c.data["bot"]["log_file"] = str(tmp_path / "bot.log")
    c.data["bot"]["reply_confirm"] = False
    c.data["alerts"]["file"] = str(tmp_path / "alerts.jsonl")
    c.data["queue"]["path"] = str(tmp_path / "queue.json")
    c.data["schedule"]["path"] = str(tmp_path / "schedule.json")
    c.data["web"]["access_log"] = str(tmp_path / "access.jsonl")
    c.data["safety"]["max_rss_per_transfer"] = 300_000_000
    return c


@pytest.fixture()
def bank(cfg):
    b = BankStore(cfg, path=cfg.get("bank.path"))
    b.roster.set_member("arken_ega", "R5")
    b.roster.set_member("officer", "R4")
    b.roster.set_member("member", "R1")
    b.credit("arken_ega", {"food": 50_000_000, "stone": 10_000_000, "wood": 5_000_000,
                          "ore": 2_000_000, "gold": 1_000_000})
    return b


@pytest.fixture()
def ops():
    return MockOps()


@pytest.fixture()
def bot(cfg, bank, ops):
    from lmbot.bot import Bot

    return Bot(cfg, ops, bank=bank)


@pytest.fixture(autouse=True)
def _clean_runtime_logs():
    """State & log runtime tidak boleh bocor antar test."""
    for name in ("bank.json", "demo.json", "transactions.jsonl", "queue.json",
                 "schedule.json"):
        (ROOT / "state" / name).unlink(missing_ok=True)
    yield
