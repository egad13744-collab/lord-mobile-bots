"""Terminal UI bot (dijalankan di dalam sesi RDP Windows)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .bot import Bot, setup_logging
from .config import ConfigError, load_config
from .device import DeviceError
from .ops import AdbOps, MockOps, OpsError

BANNER = r"""
 _     __  __ ____        _
| |   |  \/  |  _ \      | |__
| |   | |\/| | |_) | ___ | '_ \
| |___| |  | |  _ < / _ \| |_) |
|_____|_|  |_|_| \_\___/ |_.__/   v{v}
Guild Bank Bot — Lord Mobile | MuMu + ADB (tanpa modifikasi game)
"""


def _print_banner() -> None:
    print(BANNER.format(v=__version__))


def _use_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


class C:
    ok = "\033[92m" if _use_color() else ""
    err = "\033[91m" if _use_color() else ""
    dim = "\033[90m" if _use_color() else ""
    cmd = "\033[96m" if _use_color() else ""
    end = "\033[0m" if _use_color() else ""


def build_bot(args) -> Bot:
    cfg = load_config(args.config)
    if args.dry_run:
        cfg.data["bot"]["dry_run"] = True
    logger = setup_logging(cfg, verbose=args.verbose)

    if cfg.get("device.driver") == "mock" or args.dry_run:
        ops = MockOps()
        logger.info("driver: MOCK (dry-run, tidak menyentuh emulator)")
    else:
        from .device import build_driver
        from .vision import TemplateMatcher

        driver = build_driver(cfg, logger=logger.info)
        driver.connect()
        matcher = TemplateMatcher(
            cfg.resolve_path(cfg.get("templates.dir", "assets/templates")),
            float(cfg.get("templates.threshold", 0.86)),
        )
        ops = AdbOps(cfg, driver, logger=logger.info, matcher=matcher)
        logger.info(f"driver: ADB {cfg.get('device.serial')} ({driver.width}x{driver.height})")
    return Bot(cfg, ops, logger=logger)


# --------------------------------------------------------------------------- #
# Subcommand: doctor
# --------------------------------------------------------------------------- #
def cmd_doctor(args) -> int:
    cfg = load_config(args.config)
    print("🔎 Pemeriksaan lingkungan\n")
    checks = []

    adb = cfg.get("device.adb_path", "adb")
    found = bool(shutil.which(adb) or (Path(adb).exists() if adb else False))
    checks.append(("adb ditemukan", found, str(adb)))

    dev = cfg.section("device")
    checks.append(("resolusi", True, f"{dev['width']}x{dev['height']}"))
    checks.append(("serial", True, str(dev.get("serial"))))

    if dev.get("driver") == "adb" and found:
        from .device import AdbDriver

        drv = AdbDriver(adb, dev.get("serial"), dev["width"], dev["height"],
                        dev.get("auto_connect", True), logger=print)
        try:
            drv.connect()
            checks.append(("koneksi device", True, "terhubung"))
            try:
                shot = drv.screenshot()
                checks.append(("screenshot", True, f"{len(shot.data)} byte"))
            except DeviceError as exc:
                checks.append(("screenshot", False, str(exc)))
        except DeviceError as exc:
            checks.append(("koneksi device", False, str(exc)))
    else:
        checks.append(("koneksi device", False, "dilewati (driver=mock / adb tak ada)"))

    cfg_dir = cfg.resolve_path(cfg.get("flows.dir", "config/flows"))
    flows = sorted(p.stem for p in Path(cfg_dir).glob("*.yaml")) if Path(cfg_dir).exists() else []
    checks.append(("flow YAML", True, f"{len(flows)}: {', '.join(flows[:6])}" + ("..." if len(flows) > 6 else "")))

    tdir = cfg.resolve_path(cfg.get("templates.dir", "assets/templates"))
    templates = sorted(p.stem for p in Path(tdir).glob("*.png")) if Path(tdir).exists() else []
    checks.append(("template PNG", True, f"{len(templates)} file" if templates else "belum ada (opsional)"))

    try:
        from .vision import HAS_CV

        checks.append(("OpenCV", True, "aktif" if HAS_CV else "fallback murni-Python (opsional)"))
    except Exception:
        checks.append(("OpenCV", True, "fallback murni-Python"))

    ok_all = True
    for name, ok, detail in checks:
        mark = f"{C.ok}✔{C.end}" if ok else f"{C.err}✘{C.end}"
        print(f" {mark} {name:<18} {C.dim}{detail}{C.end}")
        ok_all &= ok
    print()
    print("Semua siap." if ok_all else "Ada yang perlu dibetulkan — lihat docs/SETUP-WINDOWS.md")
    return 0 if ok_all else 1


# --------------------------------------------------------------------------- #
# Subcommand: serve / run
# --------------------------------------------------------------------------- #
def _repl(bot: Bot) -> None:
    print(C.dim + "Ketik perintah (contoh: !bal)  |  :help  :stats  :quit" + C.end)
    while True:
        try:
            line = input(C.cmd + "lmbot> " + C.end)
        except (EOFError, KeyboardInterrupt):
            print()
            return
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {":quit", ":q", ":exit"}:
            return
        if stripped in {":help", ":h", "help"}:
            from .handlers import help_text

            print(help_text(bot.cfg))
            continue
        if stripped == ":stats":
            st = bot.bank.stats()
            print(json.dumps(st, indent=2, ensure_ascii=False))
            print(bot.summary())
            continue
        reply = bot.handle_line(stripped)
        if reply.message:
            color = C.ok if reply.ok else C.err
            for row in reply.message.splitlines():
                print(f"{color}{row}{C.end}")
            print(C.dim + f"  ({reply.duration_ms} ms){C.end}")


def cmd_serve(args) -> int:
    bot = build_bot(args)
    _print_banner()
    print(f"{C.ok}bot aktif{C.end} — {bot.summary()}")

    if args.once:
        for text in args.once:
            reply = bot.handle_line(text)
            print(f"> {text}\n{reply.message}\n")
        return 0

    source = args.source or "terminal"
    srv = None
    if source == "http" or args.http_port:
        from .chat import start_http

        srv = start_http(bot, host=args.http_host, port=args.http_port or 8080, token=args.token or "")
        print(f"webhook: http://{args.http_host}:{srv.server_address[1]}/  (POST {{\"text\":\"!bal\"}})")
    if source == "http":
        # mode server murni: tetap tampilkan REPL lokal
        _repl(bot)
        return 0
    if source == "file":
        from .chat import tail_source

        path = args.file or "state/commands.txt"
        print(C.dim + f"membaca perintah dari {path} (format: sender|!cmd)" + C.end)
        for text, sender in tail_source(bot.cfg.resolve_path(path)):
            reply = bot.handle_and_reply(text, sender or None)
            if reply.message:
                print(f"[{reply.sender}] {text} -> {reply.message.splitlines()[0]}")
        return 0
    if source == "chat":
        from .chat import chat_source

        try:
            for text, sender in chat_source(bot.ops, poll=float(bot.cfg.get("bot.poll_interval", 3))):
                reply = bot.handle_and_reply(text, sender or None)
                print(f"[{sender}] {text} -> {reply.message.splitlines()[0] if reply.message else ''}")
        except (OpsError, KeyboardInterrupt) as exc:
            print(f"{C.err}{exc}{C.end}")
            return 1
        return 0

    _repl(bot)
    return 0


# --------------------------------------------------------------------------- #
# Subcommand: cmd (satu perintah)
# --------------------------------------------------------------------------- #
def cmd_once(args) -> int:
    bot = build_bot(args)
    text = " ".join(args.text).strip()
    if not text:
        print("pakai: lmbot cmd \"!bal\"")
        return 2
    reply = bot.handle_line(text, args.sender)
    print(reply.message or ("ok" if reply.ok else "gagal"))
    return 0 if reply.ok else 1



# --------------------------------------------------------------------------- #
# Subcommand: demo (simulasi penuh tanpa emulator)
# --------------------------------------------------------------------------- #
DEMO_SCENARIO = [
    ("lady_ayu", "!whitelist budi R2"),
    ("lady_ayu", "!whitelist officer R4"),
    ("lady_ayu", "!setbal budi food 20m"),
    ("lady_ayu", "!setbal budi ore 3m"),
    ("lady_ayu", "!bal"),
    ("budi", "!food 5m"),
    ("lady_ayu", "!transfer budi ore 1m"),
    ("officer", "!adminbal budi"),
    ("budi", "!relocate 100 200"),
    ("officer", "!shield"),
    ("officer", "!joinca 1 F"),
    ("officer", "!findtile food 4 chat"),
    ("lady_ayu", "!stop 1800"),
    ("budi", "!food 5m"),
    ("lady_ayu", "!abort"),
    ("lady_ayu", "!members"),
    ("lady_ayu", "!stats all"),
    ("budi", "!bulanbaru"),
]


def cmd_demo(args) -> int:
    from .bot import Bot
    from .ops import MockOps

    cfg = load_config(args.config)
    cfg.data["device"]["driver"] = "mock"
    cfg.data["bot"]["reply_confirm"] = False
    cfg.data["bot"]["log_file"] = "logs/demo.log"
    cfg.data["bank"]["path"] = args.state
    bank_path = cfg.resolve_path(args.state)
    if bank_path.exists() and not args.keep:
        bank_path.unlink()
    logger = setup_logging(cfg, verbose=False)
    logger.setLevel("WARNING")
    for h in logger.handlers:
        h.setLevel("WARNING")
    ops = MockOps()
    bot = Bot(cfg, ops, logger=logger)
    bot.bank.roster.set_member("lady_ayu", "R5")
    bot.bank.credit("lady_ayu", {"food": 100_000_000, "stone": 5_000_000, "wood": 5_000_000,
                                 "ore": 5_000_000, "gold": 1_000_000})

    _print_banner()
    print(f"{C.dim}Simulasi: tidak ada perintah yang sampai ke emulator.{C.end}\n")
    lines = []
    for sender, text in DEMO_SCENARIO:
        reply = bot.handle_line(text, sender)
        color = C.ok if reply.ok else C.err
        head = f"[{sender}] {text}"
        body = reply.message.splitlines()
        print(f"{C.cmd}{head}{C.end}")
        for row in body:
            print(f"   {color}{row}{C.end}")
        print(C.dim + f"   ({reply.duration_ms} ms){C.end}\n")
        lines.append(f"```\n{head}\n" + "\n".join("   " + b for b in body) + "\n```")
    print(f"{C.ok}selesai{C.end} — {bot.summary()}")
    print(C.dim + f"state demo: {bank_path}  (hapus dengan --clean)" + C.end)
    return 0


# --------------------------------------------------------------------------- #
# Subcommand: bank (admin saldo & whitelist dari terminal)
# --------------------------------------------------------------------------- #
def cmd_bank(args) -> int:
    from .state import BankStore
    from .utils import human, parse_amount

    cfg = load_config(args.config)
    bank = BankStore(cfg)
    act = args.bank_action

    if act == "add":
        rss = {k: parse_amount(v) for k, v in zip(
            ("food", "stone", "wood", "ore", "gold"), args.amount)}
        print(json.dumps(bank.credit(args.nick, rss, note="topup manual", actor="cli"),
                         indent=2, ensure_ascii=False))
    elif act == "list":
        rows = bank.leaderboard(args.key, limit=args.limit)
        print(f"{'nick':<20}{args.key:>14}")
        for nick, val in rows:
            print(f"{nick:<20}{human(val):>14}")
    elif act == "show":
        print(json.dumps(bank.balance(args.nick), indent=2, ensure_ascii=False))
    elif act == "whitelist":
        bank.roster.set_member(args.nick, args.rank)
        bank.save()
        print(f"{args.nick} -> {args.rank}")
    elif act == "blacklist":
        bank.roster.blacklist_add(args.nick)
        bank.save()
        print(f"{args.nick} di-blacklist")
    elif act == "unfreeze":
        bank.unfreeze("cli")
        print("bank aktif kembali")
    elif act == "sync":
        print(json.dumps(bank.stats(), indent=2, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------- #
# Subcommand: record (bantu kalibrasi koordinat)
# --------------------------------------------------------------------------- #
def cmd_record(args) -> int:
    cfg = load_config(args.config)
    if cfg.get("device.driver") == "mock":
        print("driver mock tidak bisa screenshot")
        return 1
    from .device import build_driver

    drv = build_driver(cfg, logger=print)
    drv.connect()
    out = Path(args.out)
    shot = drv.screenshot()
    shot.save(out)
    print(f"screenshot disimpan: {out} ({drv.width}x{drv.height})")
    print("Buka gambar itu, catat posisi tombol dalam piksel, lalu tulis sebagai fraksi:")
    print(f"  fraksi_x = x / {drv.width}, fraksi_y = y / {drv.height}")
    print("Masukkan hasilnya ke config/flows/*.yaml (lihat docs/CALIBRATION.md).")
    return 0


# --------------------------------------------------------------------------- #
def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="lmbot",
        description="Bot Guild Bank Lord Mobile (MuMu + ADB) — jalankan di terminal RDP Windows.",
    )
    ap.add_argument("--config", "-c", default=None, help="path settings.yaml")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="simulasi tanpa menyentuh emulator")
    ap.add_argument("--version", action="version", version=f"lmbot {__version__}")
    sub = ap.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="jalankan bot (interaktif)")
    p_serve.add_argument("--source", choices=["terminal", "file", "http", "chat"], default="terminal")
    p_serve.add_argument("--file", default=None, help="path file perintah (source=file)")
    p_serve.add_argument("--http-port", type=int, default=0, help="aktifkan webhook di port ini")
    p_serve.add_argument("--http-host", default="0.0.0.0")
    p_serve.add_argument("--token", default=os.environ.get("LMBOT_TOKEN", ""))
    p_serve.add_argument("--once", nargs="*", help="jalankan perintah lalu keluar")
    p_serve.set_defaults(func=cmd_serve)

    p_once = sub.add_parser("cmd", help="jalankan satu perintah")
    p_once.add_argument("text", nargs="+")
    p_once.add_argument("--sender", default=None)
    p_once.set_defaults(func=cmd_once)

    p_doc = sub.add_parser("doctor", help="cek adb, emulator, flow, template")
    p_doc.set_defaults(func=cmd_doctor)

    p_bank = sub.add_parser("bank", help="admin saldo & whitelist dari terminal")
    bsub = p_bank.add_subparsers(dest="bank_action", required=True)
    p_add = bsub.add_parser("add")
    p_add.add_argument("nick")
    p_add.add_argument("--amount", nargs=5, default=["0", "0", "0", "0", "0"],
                       metavar=("FOOD", "STONE", "WOOD", "ORE", "GOLD"))
    p_add.set_defaults(func=cmd_bank)
    p_list = bsub.add_parser("list")
    p_list.add_argument("--key", default="food", choices=["food", "stone", "wood", "ore", "gold"])
    p_list.add_argument("--limit", type=int, default=15)
    p_list.set_defaults(func=cmd_bank)
    p_show = bsub.add_parser("show")
    p_show.add_argument("nick")
    p_show.set_defaults(func=cmd_bank)
    p_wl = bsub.add_parser("whitelist")
    p_wl.add_argument("nick")
    p_wl.add_argument("--rank", default="R2")
    p_wl.set_defaults(func=cmd_bank)
    p_bl = bsub.add_parser("blacklist")
    p_bl.add_argument("nick")
    p_bl.set_defaults(func=cmd_bank)
    p_uf = bsub.add_parser("unfreeze")
    p_uf.set_defaults(func=cmd_bank)
    p_sync = bsub.add_parser("sync")
    p_sync.set_defaults(func=cmd_bank)

    p_demo = sub.add_parser("demo", help="simulasi semua fitur tanpa emulator")
    p_demo.add_argument("--state", default="state/demo.json", help="file state simulasi")
    p_demo.add_argument("--keep", action="store_true", help="jangan hapus state lama")
    p_demo.set_defaults(func=cmd_demo)

    p_rec = sub.add_parser("record", help="ambil screenshot untuk kalibrasi koordinat")
    p_rec.add_argument("--out", default="logs/screen.png")
    p_rec.set_defaults(func=cmd_record)

    args = ap.parse_args(argv)
    if not hasattr(args, "func"):
        ap.print_help()
        return 0
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"konfigurasi: {exc}")
        return 2
    except DeviceError as exc:
        print(f"perangkat: {exc}")
        return 3
    except KeyboardInterrupt:
        print("\nberhenti.")
        return 0
