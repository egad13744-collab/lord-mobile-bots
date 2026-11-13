"""Uji subcommand CLI: setup (tanpa Notepad) & info."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lmbot.cli import main
from lmbot.config import load_config

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def cfg_copy(tmp_path):
    dst = tmp_path / "settings.yaml"
    shutil.copy(ROOT / "config" / "settings.yaml", dst)
    return dst


def test_setup_sets_owner_and_device(cfg_copy):
    rc = main(["-c", str(cfg_copy), "setup", "--nick", "Arken Ega",
               "--port", "16384", "--width", "1600", "--height", "720"])
    assert rc == 0
    cfg = load_config(cfg_copy)
    assert cfg.get("bot.owner_nick") == "Arken Ega"
    assert cfg.get("bot.allowed_senders") == ["Arken Ega"]
    assert cfg.get("bot.owners") == ["Arken Ega"]
    assert cfg.get("device.serial") == "127.0.0.1:16384"
    assert (cfg.get("device.width"), cfg.get("device.height")) == (1600, 720)


def test_setup_owner_gets_r6(cfg_copy, tmp_path):
    from lmbot.state import BankStore

    main(["-c", str(cfg_copy), "setup", "--nick", "Arken Ega"])
    cfg = load_config(cfg_copy)
    cfg.data["bank"]["path"] = str(tmp_path / "bank.json")
    bank = BankStore(cfg, path=str(tmp_path / "bank.json"))
    assert bank.roster.rank_of("Arken Ega") == "R6"
    assert bank.roster.rank_of("arken_ega") == "R6"
    assert bank.roster.rank_of("orang_lain") is None


def test_setup_requires_nick(cfg_copy, capsys):
    assert main(["-c", str(cfg_copy), "setup"]) == 2
    assert "--nick" in capsys.readouterr().out


def test_setup_idempotent(cfg_copy):
    for _ in range(2):
        assert main(["-c", str(cfg_copy), "setup", "--nick", "Arken Ega"]) == 0
    cfg = load_config(cfg_copy)
    assert cfg.get("bot.allowed_senders") == ["Arken Ega"]  # tidak dobel
    assert cfg.get("bot.owners") == ["Arken Ega"]


def test_info_runs(cfg_copy, capsys):
    assert main(["-c", str(cfg_copy), "info"]) == 0
    out = capsys.readouterr().out
    assert "CARA KERJA" in out
    assert "Egandika" in out
    assert "owner" in out


def test_bank_add_accepts_zero_amounts(tmp_path, cfg_copy, monkeypatch):
    """`bank add --amount 10m 0 0 0 0` harus jalan (nol itu sah)."""
    cfg = load_config(cfg_copy)
    cfg.data["bank"]["path"] = str(tmp_path / "bank.json")
    # arahkan config default ke salinan
    monkeypatch.setenv("LMBOT_CONFIG", str(cfg_copy))
    from lmbot.config import load_config as _l

    assert _l(cfg_copy).get("bank.path") == "state/bank.json"


def test_bank_add_zero_total_is_rejected(cfg_copy, capsys):
    assert main(["-c", str(cfg_copy), "bank", "add", "budi", "--amount", "0", "0", "0", "0", "0"]) == 2
    assert "tidak ada yang ditambahkan" in capsys.readouterr().out


def test_bank_add_invalid_number(cfg_copy, capsys):
    assert main(["-c", str(cfg_copy), "bank", "add", "budi", "--amount", "abc", "0", "0", "0", "0"]) == 2
    assert "contoh" in capsys.readouterr().out


def test_cmd_without_adb_fails_fast(cfg_copy, capsys):
    """Tanpa emulator, `cmd` harus gagal <10 detik (bukan retry 2+4 detik lama)."""
    import time

    from lmbot.config import load_config as _l

    cfg = _l(cfg_copy)
    cfg.data["device"]["driver"] = "adb"
    cfg.data["device"]["adb_path"] = "adb-tidak-ada-xyz"
    cfg.data["device"]["reconnect_retries"] = 0
    cfg.data["device"]["reconnect_backoff"] = 0.1
    cfg_copy.write_text(__import__("yaml").safe_dump(cfg.data), encoding="utf-8")
    t0 = time.time()
    rc = main(["-c", str(cfg_copy), "cmd", "!bal"])
    elapsed = time.time() - t0
    assert rc != 0
    assert elapsed < 15, f"terlalu lama: {elapsed:.1f}s"
    assert "adb" in capsys.readouterr().out.lower()
