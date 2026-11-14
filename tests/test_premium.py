"""Regresi fitur premium baru; semuanya dapat diuji tanpa MuMu/ADB."""
from __future__ import annotations

import json
import time

import pytest

from lmbot.i18n import Translator
from lmbot.ledger import verify_chain
from lmbot.ocr import parse_number
from lmbot.parser import parse
from lmbot.schedule import CronError, Schedule, describe, matches, parse_cron
from lmbot.state import BankStore
from lmbot.tasks import TaskQueue


def test_cron_parse_and_safe_schedule(tmp_path):
    schedule = Schedule(tmp_path / "schedule.json")
    job = schedule.add("0 2 * * *", "!top food", "arken_ega")
    assert job.id == 1
    assert parse_cron("*/15 0-6 * * 1,3")
    assert describe("0 2 * * *") == "harian 02:00"
    t = time.struct_time((2026, 11, 13, 2, 0, 0, 4, 317, -1))
    assert matches("0 2 * * *", t)
    with pytest.raises(CronError):
        schedule.add("* * *", "!sync", "x")
    with pytest.raises(CronError, match="perintah baca"):
        schedule.add("0 2 * * *", "!stop 3600", "arken_ega")


def test_cron_command_parser_preserves_expression():
    cmd = parse('!cron add "0 2 * * *" !top food', "arken_ega")
    assert cmd.name == "cron"
    assert cmd.args == {"action": "add", "expr": "0 2 * * *", "text": "!top food"}


def test_queue_priorities_and_crash_recovery(tmp_path):
    path = tmp_path / "queue.json"
    q = TaskQueue(path)
    low = q.add("!top", "member", "R1")
    high = q.add("!top", "owner", "R6")
    assert q.next_job().id == high.id
    q2 = TaskQueue(path)
    assert q2.list(status="queued")[0].id == high.id
    assert q2.list(status="queued")[1].id == low.id
    assert q2.next_job().id == high.id


def test_hash_chain_undo_and_quota(cfg, tmp_path):
    cfg.data["bank"]["path"] = str(tmp_path / "bank.json")
    bank = BankStore(cfg, path=cfg.get("bank.path"))
    bank.credit("member", {"food": 100})
    bank.debit("member", {"food": 25}, note="penyesuaian manual")
    assert bank.verify_audit()[0]
    assert bank.quota_used("member", "food") == 0  # debit manual bukan pengiriman
    entry, balance = bank.undo_last("admin")
    assert entry["kind"] == "debit" and balance["food"] == 100
    previous, balance = bank.undo_last("admin")
    assert previous["kind"] == "credit" and previous["id"] != entry["id"]
    assert balance["food"] == 0
    assert bank.undo_last("admin")[0] is None
    assert bank.verify_audit()[0]
    bank.credit("member", {"food": 100}, note="deposit")
    bank.debit("member", {"food": 25}, note="transfer ke target")
    assert bank.quota_used("member", "food") == 25
    lines = (tmp_path / "transactions.jsonl").read_text().splitlines()
    row = json.loads(lines[0]); row["rss"]["food"] = 101
    lines[0] = json.dumps(row)
    (tmp_path / "transactions.jsonl").write_text("\n".join(lines) + "\n")
    assert verify_chain(tmp_path / "transactions.jsonl")[0] is False


def test_i18n_fallback_and_number_parser():
    assert "Queue" in Translator("en")("queue.empty")
    assert Translator("xx")("audit.ok", count=3).endswith("3 entri)")
    assert parse_number("1,234,567") == 1234567
    assert parse_number("12.5m") == 12500000
    assert parse_number("45k") == 45000
    assert parse_number("not a number") is None


def test_bot_alias_quota_undo_and_cron(bot, cfg):
    cfg.data["safety"]["daily_limit_per_type"] = 100
    # Alias dari config kustom harus bekerja tanpa mengubah perintah inti.
    assert bot.handle_line("!b", "arken_ega").ok
    # Kuota langsung dihitung dari ledger (debit oleh handler adalah transaksi).
    bot.bank.credit("arken_ega", {"food": 1000})
    bot.bank.debit("arken_ega", {"food": 50}, note="transfer test")
    assert bot.bank.quota_used("arken_ega", "food") == 50
    assert bot.handle_line("!audit verify", "arken_ega").ok
    assert bot.handle_line("!cron add \"0 2 * * *\" !top food", "arken_ega").ok
    assert bot.handle_line("!cron list", "arken_ega").ok


def test_digit_ocr_train_and_read(tmp_path):
    from lmbot.imaging import Image
    from lmbot.ocr import DigitOCR, train_digits

    patterns = {
        0:["111","101","101","101","101","101","111"],
        1:["010","110","010","010","010","010","111"],
        2:["111","001","001","111","100","100","111"],
        3:["111","001","001","111","001","001","111"],
        4:["101","101","101","111","001","001","001"],
        5:["111","100","100","111","001","001","111"],
        6:["111","100","100","111","101","101","111"],
        7:["111","001","001","001","001","001","001"],
        8:["111","101","101","111","101","101","111"],
        9:["111","101","101","111","001","001","111"],
    }
    def draw(seq):
        width, height = 190, 38
        buf = bytearray(width * height)
        x = 5
        for char in seq:
            for row, line in enumerate(patterns[int(char)]):
                for col, bit in enumerate(line):
                    if bit == "1":
                        for dy in range(4):
                            for dx in range(4):
                                buf[(5 + row * 4 + dy) * width + x + col * 4 + dx] = 255
            x += 18
        return Image(width, height, 1, bytes(buf))
    sample = tmp_path / "sample.png"
    draw("0123456789").save_png(sample)
    train_digits(sample, (0, 0, 1, 1), tmp_path / "ocr", save_preview=False)
    reader = DigitOCR(tmp_path / "ocr")
    assert reader.ready
    assert reader.read_image(draw("1234")).text == "1234"


def test_instance_profile_state_isolation():
    from lmbot.config import load_config
    cfg = load_config(profile="emu-test")
    assert cfg.get("device.serial") == "127.0.0.1:16384"
    assert cfg.get("bank.path") == "state/emu-test/bank.json"
    assert cfg.get("queue.path") == "state/emu-test/queue.json"


def test_daily_quota_is_enforced_before_transfer(bot, cfg):
    cfg.data["safety"]["daily_limit_per_type"] = 100
    reply = bot.handle_line("!transfer member food 200", "arken_ega")
    assert not reply.ok
    assert "kuota" in reply.message.lower()
    assert bot.bank.balance("arken_ega")["food"] == 50_000_000


def test_deferred_queue_worker_does_not_requeue(bot):
    from lmbot.ops import DEVICE_LOCK
    import threading
    locked = threading.Event()
    release = threading.Event()
    def hold_device():
        with DEVICE_LOCK:
            locked.set()
            release.wait(2)
    holder = threading.Thread(target=hold_device)
    holder.start()
    assert locked.wait(1)
    try:
        reply = bot.handle_line("!transfer member food 1m", "arken_ega")
        assert reply.ok and "Antrian" in reply.message
    finally:
        release.set()
        holder.join(1)
    bot.start_workers()
    deadline = time.time() + 4
    try:
        while time.time() < deadline and bot.queue.stats()["queued"]:
            time.sleep(0.05)
        # Wait for the worker to finish the executing job too.
        while time.time() < deadline and bot.queue.stats()["running"]:
            time.sleep(0.05)
        stats = bot.queue.stats()
        assert stats["done"] == 1
        assert stats["queued"] == 0
        assert bot.bank.balance("member")["food"] == 1_000_000
    finally:
        bot.stop_workers()


def test_undo_refuses_to_rewrite_completed_game_transfer(cfg, tmp_path):
    cfg.data["bank"]["path"] = str(tmp_path / "bank.json")
    bank = BankStore(cfg, path=cfg.get("bank.path"))
    bank.credit("sender", {"food": 500}, note="deposit")
    bank.debit("sender", {"food": 100}, note="transfer ke receiver")
    bank.credit("receiver", {"food": 100}, note="transfer dari sender")
    assert bank.undo_last("admin") == (None, None)
    assert bank.balance("sender")["food"] == 400
    assert bank.balance("receiver")["food"] == 100


def test_failed_game_refund_does_not_consume_quota(cfg, tmp_path):
    cfg.data["bank"]["path"] = str(tmp_path / "bank.json")
    bank = BankStore(cfg, path=cfg.get("bank.path"))
    bank.credit("sender", {"food": 100})
    bank.debit("sender", {"food": 40}, note="transfer ke receiver")
    bank.credit("sender", {"food": 40}, note="refund gagal kirim")
    assert bank.quota_used("sender", "food") == 0


def test_total_daily_limit_and_quota_display(bot, cfg):
    cfg.data["safety"]["daily_limit_all_types"] = 100
    reply = bot.handle_line("!transfer member food 200", "arken_ega")
    assert not reply.ok and "kuota" in reply.message.lower()
    quota = bot.handle_line("!quota", "arken_ega")
    assert quota.ok and "Total:" in quota.message


def test_legacy_audit_is_unverified_and_disables_undo(cfg, tmp_path):
    cfg.data["bank"]["path"] = str(tmp_path / "bank.json")
    bank = BankStore(cfg, path=cfg.get("bank.path"))
    bank.credit("member", {"food": 10}, note="deposit")
    path = tmp_path / "transactions.jsonl"
    row = json.loads(path.read_text().splitlines()[0])
    row.pop("hash")
    row.pop("prev_hash")
    path.write_text(json.dumps(row) + "\n")
    assert bank.verify_audit()[0] is False
    assert bank.undo_last("admin") == (None, None)
    assert bank.balance("member")["food"] == 10
