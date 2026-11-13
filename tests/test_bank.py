"""Uji tanpa emulator: domain bank (parser, saldo, otorisasi, rate limit)."""
from __future__ import annotations

import json
import pytest

from lmbot.bot import Bot
from lmbot.handlers import Cmd, Context, Handlers
from lmbot.ops import MockOps, OpsError
from lmbot.parser import UnknownCommand, parse
from lmbot.roles import PermissionError_, Roster
from lmbot.state import BankStore, InsufficientFunds
from lmbot.utils import ParseError, human, parse_amount, parse_rss_vector


# --------------------------------------------------------------------------- #
# parser & angka
# --------------------------------------------------------------------------- #
def test_parse_amount_suffixes():
    assert parse_amount("100m") == 100_000_000
    assert parse_amount("1.5k") == 1500
    assert parse_amount("250") == 250
    assert parse_amount("1,5m") == 1_500_000
    assert parse_amount("1,000") == 1000


def test_parse_amount_invalid():
    for bad in ("", "abc", "-5m", "10x", "0"):
        with pytest.raises(ParseError):
            parse_amount(bad)


def test_parse_rss_vector():
    vec = parse_rss_vector("5m 0 1k 0 0")
    assert vec == {"F": 5_000_000, "S": 0, "W": 1000, "O": 0, "G": 0}
    assert parse_rss_vector("5m,5m,5m,5m,5m")["G"] == 5_000_000
    with pytest.raises(ParseError):
        parse_rss_vector("1m 1m 1m 1m 1m 1m")


def test_human():
    assert human(1_500_000) == "1.5M"
    assert human(2500) == "2.5K"
    assert human(42) == "42"


@pytest.mark.parametrize(
    "text,name,key,value",
    [
        ("!bal", "bal", None, None),
        ("!stats all", "stats_all", None, None),
        ("!stop 3600", "stop", "duration", "3600"),
        ("!relocate 123 456", "relocate", "x", "123"),
        ("!joinca 1 F", "joincha", "f", True),
        ("!findtile food 4 chat", "findtile", "chat", True),
        ("!transfer lady_ayu ore 100m", "transfer", "amount", "100m"),
        ("!rss 5m 5m 5m 5m 5m", "rss", "g", "5m"),
        ("!food 100m", "rss_food", "amount", "100m"),
        ("!buildspam stop", "buildspam_stop", None, None),
    ],
)
def test_parse_commands(text, name, key, value):
    cmd = parse(text)
    assert cmd.name == name
    if key:
        assert cmd.args[key] == value


def test_parse_unknown():
    with pytest.raises(UnknownCommand) as exc:
        parse("!bulanbaru")
    assert "tidak dikenal" in str(exc.value)


def test_semua_kode_pada_gambar_punya_handler(cfg, bank, ops):
    """Kontrak: setiap perintah di daftar gambar harus di-dispatch, bukan 'belum diimplementasikan'."""
    from lmbot.parser import ALL_SPECS

    h = Handlers(Context(cfg=cfg, bank=bank, ops=ops))
    missing = []
    for spec in ALL_SPECS:
        args = {p: ("1" if p not in ("type", "nick", "monster", "title", "rank") else "food")
                for p in spec.params}
        args.setdefault("nick", "member")
        result = h.dispatch(Cmd(spec.name, args, "lady_ayu", rank="R5"))
        if "belum diimplementasikan" in (result.error or ""):
            missing.append(spec.name)
    assert not missing, f"handler hilang: {missing}"


# --------------------------------------------------------------------------- #
# saldo & transaksi
# --------------------------------------------------------------------------- #
def test_credit_debit_persist(cfg, bank):
    bank.credit("member", {"food": 1000})
    assert bank.balance("member")["food"] == 1000
    bank.debit("member", {"food": 400})
    assert bank.balance("member")["food"] == 600
    reloaded = BankStore(cfg, path=cfg.get("bank.path"))
    assert reloaded.balance("member")["food"] == 600


def test_debit_insufficient(bank):
    with pytest.raises(InsufficientFunds):
        bank.debit("member", {"food": 1})


def test_audit_log_written(bank):
    bank.credit("member", {"gold": 10})
    rows = bank.recent(5)
    assert rows and rows[-1]["kind"] == "credit"
    assert bank.count_transactions() >= 1


def test_leaderboard(bank):
    rows = bank.leaderboard("food")
    assert rows[0][0] == "ladyayu"


def test_freeze_blocks_transfer(bot, bank):
    reply = bot.handle_line("!stop 600", "lady_ayu")
    assert reply.ok
    assert bank.is_frozen()
    blocked = bot.handle_line("!food 1m", "lady_ayu")
    assert not blocked.ok
    assert "dijeda" in blocked.message


# --------------------------------------------------------------------------- #
# otorisasi & whitelist
# --------------------------------------------------------------------------- #
def test_rank_required(bot):
    reply = bot.handle_line("!relocate 1 2", "member")
    assert not reply.ok
    assert "butuh R4" in reply.message


def test_blacklist_denied(bank, bot):
    bank.roster.blacklist_add("member")
    reply = bot.handle_line("!bal", "member")
    assert not reply.ok
    assert "blacklist" in reply.message


def test_unknown_sender_denied(bot):
    reply = bot.handle_line("!bal", "orang_asing")
    assert not reply.ok
    assert "whitelist" in reply.message


def test_whitelist_command_persists(bot, cfg):
    reply = bot.handle_line("!whitelist budi R3", "lady_ayu")
    assert reply.ok
    reloaded = BankStore(cfg, path=cfg.get("bank.path"))
    assert reloaded.roster.rank_of("budi") == "R3"


def test_nick_normalization_matches(bank):
    bank.credit("Budi Santoso", {"food": 5})
    assert bank.balance("budisantoso")["food"] == 5
    assert bank.balance("budi_santoso")["food"] == 5
    assert bank.roster.resolve("lady ayu")


def test_roster_roundtrip():
    r = Roster()
    r.set_member("A B", "R3")
    r.blacklist_add("bad")
    r.add_owner("owner")
    r2 = Roster.from_dict(json.loads(json.dumps(r.to_dict())))
    assert r2.rank_of("a_b") == "R3"
    assert r2.is_blacklisted("BAD")
    assert r2.rank_of("owner") == "R6"
    with pytest.raises(PermissionError_):
        r2.authorize("bad", "R1")


# --------------------------------------------------------------------------- #
# alur RSS / transfer
# --------------------------------------------------------------------------- #
def test_rss_shortcut_debits_and_sends(bot, bank, ops):
    reply = bot.handle_line("!food 1m", "lady_ayu")
    assert reply.ok, reply.message
    assert bank.balance("lady_ayu")["food"] == 49_000_000
    assert ops.calls[-1][0] == "send_rss_to_member"
    assert ops.calls[-1][2] == {"food": 1_000_000}


def test_rss_full_vector(bot, bank):
    reply = bot.handle_line("!rss 1m 0 0 0 0", "lady_ayu")
    assert reply.ok, reply.message
    assert bank.balance("lady_ayu")["food"] == 49_000_000


def test_refund_on_ops_failure(cfg, bank):
    class BrokenOps(MockOps):
        def send_rss_to_member(self, nick, rss):
            raise OpsError("flow belum dikalibrasi")

    bot = Bot(cfg, BrokenOps(), bank=bank)
    before = bank.balance("lady_ayu")["food"]
    reply = bot.handle_line("!food 1m", "lady_ayu")
    assert not reply.ok
    assert "dikembalikan" in reply.message
    assert bank.balance("lady_ayu")["food"] == before


def test_safety_limit(bot):
    reply = bot.handle_line("!food 999m", "lady_ayu")
    assert not reply.ok
    assert "batas aman" in reply.message


def test_transfer_to_self_rejected(bot):
    reply = bot.handle_line("!transfer lady_ayu food 1m", "lady_ayu")
    assert not reply.ok
    assert "diri sendiri" in reply.message


def test_transfer_between_members(bot, bank):
    bank.credit("member", {"ore": 5_000_000})
    reply = bot.handle_line("!transfer member ore 1m", "lady_ayu")
    assert reply.ok, reply.message
    assert bank.balance("lady_ayu")["ore"] == 1_000_000
    assert bank.balance("member")["ore"] == 6_000_000


def test_setbal_requires_r5(bot, bank):
    assert not bot.handle_line("!setbal member food 1m", "officer").ok
    assert bot.handle_line("!setbal member food 1m", "lady_ayu").ok
    assert bank.balance("member")["food"] == 1_000_000


def test_abort_freezes(bot, bank):
    assert bot.handle_line("!abort", "lady_ayu").ok
    assert bank.is_frozen()


# --------------------------------------------------------------------------- #
# rate limit & prefix
# --------------------------------------------------------------------------- #
def test_rate_limit(cfg, bank, ops):
    cfg.data["bot"]["max_commands_per_minute"] = 3
    bot = Bot(cfg, ops, bank=bank)
    results = [bot.handle_line("!shield", "lady_ayu").ok for _ in range(5)]
    assert results[:3] == [True, True, True]
    assert results[3] is False


def test_prefix_filter(bot):
    assert bot.handle_line("halo semua", "lady_ayu").message == ""
    assert bot.handle_line("[R4] !shield", "lady_ayu").ok


def test_dry_run_never_touches_game(cfg, bank, ops):
    cfg.data["bot"]["dry_run"] = True
    bot = Bot(cfg, ops, bank=bank)
    bot.handle_line("!food 1m", "lady_ayu")
    assert not [c for c in ops.calls if c[0] == "send_rss_to_member"]


# --------------------------------------------------------------------------- #
# fitur lanjutan: help/top/sync, konfirmasi 2 langkah, alert, chat_tail, lock
# --------------------------------------------------------------------------- #
def test_help_command(bot):
    assert bot.handle_line("!help", "lady_ayu").ok
    rss = bot.handle_line("!help RSS", "lady_ayu")
    assert rss.ok and "RSS" in rss.message


def test_top_command(bot, bank):
    bank.credit("member", {"gold": 7})
    reply = bot.handle_line("!top gold", "lady_ayu")
    assert reply.ok and "member" in reply.message


def test_sync_reports_total(bot, bank):
    reply = bot.handle_line("!sync", "lady_ayu")
    assert reply.ok and "Saldo tercatat" in reply.message


def test_confirm_two_step(bot, ops):
    first = bot.handle_line("!guild AYU", "lady_ayu")
    assert first.ok and "Konfirmasi" in first.message
    assert not ops.actions(), "aksi tidak boleh jalan sebelum konfirmasi"
    second = bot.handle_line("!guild AYU confirm", "lady_ayu")
    assert second.ok and "dipindahkan" in second.message
    assert ops.actions() == ["guild"]


def test_confirm_disabled(cfg, bank, ops):
    cfg.data["bot"]["confirm_risky"] = False
    bot = Bot(cfg, ops, bank=bank)
    reply = bot.handle_line("!migrate 123 4 5", "lady_ayu")
    assert reply.ok and ops.actions() == ["migrate"]


def test_confirm_relocate(bot, ops):
    assert "Konfirmasi" in bot.handle_line("!relocate 10 20", "lady_ayu").message
    assert not ops.actions()


def test_alert_on_failure(cfg, bank):
    from lmbot.alerts import AlertSink

    class BrokenOps(MockOps):
        def send_rss_to_member(self, nick, rss):
            raise OpsError("flow belum dikalibrasi")

    sink = AlertSink(cfg, path=str(cfg.root / "logs" / "test-alerts.jsonl"))
    ops = BrokenOps()
    ops.alerts = sink
    bot = Bot(cfg, ops, bank=bank)
    reply = bot.handle_line("!food 1m", "lady_ayu")
    assert not reply.ok
    rows = sink.recent()
    assert rows and rows[-1]["level"] == "error"
    assert "!food" in rows[-1]["title"]


def test_alert_throttle(cfg):
    from lmbot.alerts import AlertSink

    (cfg.root / "logs" / "thr.jsonl").unlink(missing_ok=True)
    sink = AlertSink(cfg, path=str(cfg.root / "logs" / "thr.jsonl"))
    sink.throttle = 60
    sink.send("error", "sama", "halo")
    sink.send("error", "sama", "halo lagi")
    assert len(sink.recent()) == 1


def test_alert_level_filter(cfg):
    from lmbot.alerts import AlertSink

    (cfg.root / "logs" / "lvl.jsonl").unlink(missing_ok=True)
    sink = AlertSink(cfg, path=str(cfg.root / "logs" / "lvl.jsonl"))
    sink.min_level = "error"
    sink.send("info", "diam", "tidak dicatat")
    sink.send("error", "tercatat", "ya")
    assert [r["title"] for r in sink.recent()] == ["tercatat"]


def test_chat_tail_reads_new_lines(cfg, tmp_path):
    from lmbot.device import MockDriver
    from lmbot.ops import AdbOps

    tail = tmp_path / "chat.txt"
    tail.write_text("", encoding="utf-8")
    cfg.data["ui"]["chat_tail"] = str(tail)
    ops = AdbOps(cfg, MockDriver())
    assert ops.read_chat() == []
    tail.write_text("budi: !bal\n", encoding="utf-8")
    lines = ops.read_chat()
    assert lines and lines[0].sender == "budi" and lines[0].text == "!bal"
    # baris yang sama tidak dibaca dua kali
    assert ops.read_chat() == []
    tail.write_text("budi: !bal\nofficer: !shield\n", encoding="utf-8")
    assert [ln.text for ln in ops.read_chat()] == ["!shield"]


def test_read_chat_without_tail_explains_alternatives(cfg):
    from lmbot.device import MockDriver
    from lmbot.ops import AdbOps

    cfg.data["ui"]["chat_tail"] = ""
    with pytest.raises(OpsError) as exc:
        AdbOps(cfg, MockDriver()).read_chat()
    assert "chat_tail" in str(exc.value)
    assert "terminal/file/http" in str(exc.value)


def test_device_lock_serializes_calls(cfg):
    import threading
    import time as _time

    from lmbot.ops import DEVICE_LOCK

    order = []

    def worker(tag):
        with DEVICE_LOCK:
            order.append(f"{tag}-start")
            _time.sleep(0.02)
            order.append(f"{tag}-end")

    threads = [threading.Thread(target=worker, args=(t,)) for t in "ab"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # tidak boleh berselang-seling
    assert order in (["a-start", "a-end", "b-start", "b-end"],
                     ["b-start", "b-end", "a-start", "a-end"])


# --------------------------------------------------------------------------- #
# pengiriman multi-tipe (flow per tipe) & diagnosa config
# --------------------------------------------------------------------------- #
def test_send_per_type_flow(cfg, tmp_path):
    """Bila bank_send_one_type ada, tiap tipe dikirim terpisah."""
    from lmbot.device import MockDriver
    from lmbot.ops import AdbOps

    flows = tmp_path / "flows"
    flows.mkdir()
    (flows / "bank_open_member.yaml").write_text(
        "name: bank_open_member\nsteps:\n  - type: '{nick}'\n", encoding="utf-8")
    (flows / "bank_send_one_type.yaml").write_text(
        "name: bank_send_one_type\nsteps:\n"
        "  - type: '{type}:{amount}'\n  - wait: 0\n", encoding="utf-8")
    cfg.data["flows"]["dir"] = str(flows)
    cfg.data["safety"]["cooldown_between_transfers"] = 0
    drv = MockDriver()
    ops = AdbOps(cfg, drv)
    ops.send_rss_to_member("budi", {"food": 1000, "ore": 500, "gold": 0})
    assert drv.texts() == ["food:1000", "ore:500"]


def test_send_falls_back_to_single_flow(cfg):
    from lmbot.device import MockDriver
    from lmbot.ops import AdbOps

    cfg.data["flows"]["dir"] = str(cfg.root / "config" / "flows")
    ops = AdbOps(cfg, MockDriver())
    # semua flow kirim masih enabled: false -> error yang jelas, bukan crash
    with pytest.raises(OpsError) as exc:
        ops.send_rss_to_member("budi", {"food": 1000})
    assert "dinonaktifkan" in str(exc.value)


def test_send_rejects_empty_vector(cfg):
    from lmbot.device import MockDriver
    from lmbot.ops import AdbOps

    with pytest.raises(OpsError):
        AdbOps(cfg, MockDriver()).send_rss_to_member("budi", {"food": 0})


def test_diagnostics_warn_defaults(cfg):
    from lmbot.diagnostics import warn_insecure_defaults

    emitted = []
    found = warn_insecure_defaults(cfg, emitted.append)
    assert any("lady_ayu" in m for m in found)
    assert emitted == [f"⚠️  {m}" for m in found]


def test_diagnostics_quiet_when_configured(cfg):
    from lmbot.diagnostics import warn_insecure_defaults

    cfg.data["bot"]["allowed_senders"] = ["bank_ayu"]
    cfg.data["safety"]["whitelist_enforced"] = True
    cfg.data["bot"]["confirm_risky"] = True
    cfg.data["web"]["enabled"] = False
    assert warn_insecure_defaults(cfg, lambda _m: None) == []
