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
from .about import AUTHOR_LINE, TAGLINE
from .bot import Bot, setup_logging
from .config import ConfigError, load_config
from .utils import ParseError
from .device import DeviceError
from .ops import AdbOps, MockOps, OpsError

BANNER = r"""
 _     __  __ ____        _
| |   |  \/  |  _ \      | |__
| |   | |\/| | |_) | ___ | '_ \
| |___| |  | |  _ < / _ \| |_) |
|_____|_|  |_|_| \_\___/ |_.__/   v{v}
{tagline}
{author}
"""


def _print_banner() -> None:
    print(BANNER.format(v=__version__, tagline=TAGLINE, author=AUTHOR_LINE))


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
    from .alerts import AlertSink
    from .diagnostics import warn_insecure_defaults

    if cfg.get("diagnostics.enabled", True):
        warn_insecure_defaults(cfg, logger.warning)
    alerts = AlertSink(cfg, logger)

    if cfg.get("device.driver") == "mock" or args.dry_run:
        ops = MockOps()
        ops.alerts = alerts
        logger.info("driver: MOCK (dry-run, tidak menyentuh emulator)")
    else:
        from .device import build_driver
        from .vision import TemplateMatcher

        from .device import DeviceSession

        raw_driver = build_driver(cfg, logger=logger.info)
        driver = DeviceSession(
            raw_driver,
            retries=int(cfg.get("device.reconnect_retries", 2)),
            backoff=float(cfg.get("device.reconnect_backoff", 2.0)),
            logger=logger.info,
        )
        driver.connect()
        matcher = TemplateMatcher(
            cfg.resolve_path(cfg.get("templates.dir", "assets/templates")),
            float(cfg.get("templates.threshold", 0.86)),
        )
        ops = AdbOps(cfg, driver, logger=logger.info, matcher=matcher, alerts=alerts)
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
    web_port = args.web_port or (int(bot.cfg.get("web.port", 8081)) if bot.cfg.get("web.enabled") else 0)
    if web_port:
        from .web import start_dashboard

        dash = start_dashboard(
            bot, host=bot.cfg.get("web.host", "0.0.0.0"), port=web_port,
            token=args.token or bot.cfg.get("web.token", ""),
        )
        print(f"dashboard: http://{bot.cfg.get('web.host')}:{dash.server_address[1]}/")
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
    text = " ".join(args.text).strip()
    if not text:
        print("pakai: lmbot cmd \"!bal\"")
        return 2
    bot = build_bot(args)
    reply = bot.handle_line(text, args.sender)
    print(reply.message or ("ok" if reply.ok else "gagal"))
    return 0 if reply.ok else 1



# --------------------------------------------------------------------------- #
# Subcommand: demo (simulasi penuh tanpa emulator)
# --------------------------------------------------------------------------- #
DEMO_SCENARIO = [
    ("arken_ega", "!whitelist budi R2"),
    ("arken_ega", "!whitelist officer R4"),
    ("arken_ega", "!setbal budi food 20m"),
    ("arken_ega", "!setbal budi ore 3m"),
    ("arken_ega", "!bal"),
    ("budi", "!food 5m"),
    ("arken_ega", "!transfer budi ore 1m"),
    ("officer", "!adminbal budi"),
    ("budi", "!relocate 100 200"),
    ("officer", "!shield"),
    ("officer", "!joinca 1 F"),
    ("officer", "!findtile food 4 chat"),
    ("arken_ega", "!stop 1800"),
    ("budi", "!food 5m"),
    ("arken_ega", "!abort"),
    ("arken_ega", "!members"),
    ("arken_ega", "!stats all"),
    ("budi", "!help RSS"),
    ("arken_ega", "!guild AYU"),
    ("arken_ega", "!guild AYU confirm"),
    ("budi", "!bulanbaru"),
]


def cmd_demo(args) -> int:
    from .bot import Bot
    from .ops import MockOps

    cfg = load_config(args.config)
    cfg.data["device"]["driver"] = "mock"
    cfg.data["bot"]["reply_confirm"] = False
    cfg.data["bot"]["log_file"] = "logs/demo.log"
    cfg.data["diagnostics"] = {"enabled": False}
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
    bot.bank.roster.set_member("arken_ega", "R5")
    bot.bank.credit("arken_ega", {"food": 100_000_000, "stone": 5_000_000, "wood": 5_000_000,
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
        try:
            rss = {k: parse_amount(v, allow_zero=True) for k, v in zip(
                ("food", "stone", "wood", "ore", "gold"), args.amount)}
        except ParseError as exc:
            print(f"jumlah tidak valid: {exc}")
            print('contoh: code.py bank add budi --amount 10m 0 0 0 0')
            return 2
        if not any(rss.values()):
            print("semua jumlah 0 — tidak ada yang ditambahkan")
            return 2
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
# Subcommand: template (crop otomatis dari screenshot mentah)
# --------------------------------------------------------------------------- #
def cmd_template(args) -> int:
    from .imaging import (
        EXPECTED_TEMPLATES,
        ImageError,
        list_templates,
        make_template,
    )

    cfg = load_config(args.config)
    tdir = cfg.resolve_path(cfg.get("templates.dir", "assets/templates"))

    if args.template_action == "list":
        status = list_templates(tdir)
        print(f"📁 {tdir}")
        for name, desc in EXPECTED_TEMPLATES.items():
            mark = f"{C.ok}✔{C.end}" if status[name] else f"{C.err}✘{C.end}"
            print(f" {mark} {name:<16} {C.dim}{desc}{C.end}")
        have = sum(status.values())
        print(f"\n{have}/{len(status)} template siap.")
        return 0 if have else 1

    if not args.screen:
        print("pakai: lmbot template add --screen logs/screen.png --name send_button --box 0.7,0.8,0.85,0.9")
        return 2
    try:
        box = [float(v) for v in str(args.box).replace(";", ",").split(",")]
        res = make_template(
            args.screen,
            args.name,
            box,
            tdir,
            gray=not args.color,
            scale=args.scale,
            max_width=args.max_width,
            preview=args.preview,
        )
    except ImageError as exc:
        print(f"gagal: {exc}")
        return 1
    print(f"✔ template '{res.name}' dibuat: {res.path}")
    print(f"  sumber   : {res.source_size[0]}x{res.source_size[1]}  crop px {res.box_px}")
    print(f"  template : {res.template_size[0]}x{res.template_size[1]} px")
    fx, fy, fw, fh = res.box_fraction
    print(f"  fraksi   : [{fx}, {fy}, {fw}, {fh}]")
    print(f"  untuk tap: tap: [{round(fx + fw/2, 4)}, {round(fy + fh/2, 4)}]  ← tempel di flow YAML")
    return 0


# --------------------------------------------------------------------------- #
# Subcommand: verify (uji template terhadap screenshot tanpa emulator)
# --------------------------------------------------------------------------- #
def cmd_verify(args) -> int:
    from .imaging import verify_template

    cfg = load_config(args.config)
    tdir = cfg.resolve_path(cfg.get("templates.dir", "assets/templates"))
    screen = args.screen or (args.adb and _grab(cfg, args.out))
    if not screen:
        print("pakai: lmbot verify --screen logs/screen.png [--name send_button]")
        return 2
    names = [args.name] if args.name else sorted(
        p.stem for p in Path(tdir).glob("*.png")
    )
    if not names:
        print("belum ada template di", tdir)
        return 1
    worst = 0.0
    for name in names:
        res = verify_template(screen, name, tdir, threshold=args.threshold)
        ok = res["found"]
        mark = f"{C.ok}✔{C.end}" if ok else f"{C.err}✘{C.end}"
        print(f" {mark} {name:<16} skor={res['score']:.3f} {res.get('center_fraction','')}")
        if ok:
            worst = min(worst or 1.0, float(res["score"]))
    print()
    if worst and worst < 0.75:
        print(f"{C.err}Peringatan:{C.end} skor terendah {worst:.3f} — template bisa salah "
              f"crop / beda resolusi. Crop ulang dengan box lebih tepat.")
    return 0 if worst else 1


def _grab(cfg, out: str) -> Optional[str]:
    from .device import build_driver

    drv = build_driver(cfg, logger=print)
    drv.connect()
    shot = drv.screenshot()
    path = cfg.resolve_path(out)
    shot.save(path)
    print(f"screenshot: {path} ({shot.width}x{shot.height})")
    return str(path)



# --------------------------------------------------------------------------- #
# Subcommand: setup (konfigurasi awal tanpa buka Notepad)
# --------------------------------------------------------------------------- #
def cmd_setup(args) -> int:
    """Tulis nick owner/whitelist & device ke config/settings.yaml."""
    import re

    cfg = load_config(args.config)
    path = cfg.path
    text = path.read_text(encoding="utf-8")
    nick = (args.nick or "").strip()

    if not nick:
        print("pakai: lmbot setup --nick \"Arken Ega\"")
        return 2

    changed = []
    # owner_nick
    if re.search(r"^\s*owner_nick:.*$", text, re.M):
        text = re.sub(r"^\s*owner_nick:.*$", f"  owner_nick: {nick}", text, count=1, flags=re.M)
        changed.append(f"owner_nick = {nick}")
    # allowed_senders (baris '- xxx' pertama di bawah key itu)
    if re.search(r"allowed_senders:", text):
        text = re.sub(
            r"(allowed_senders:[^\n]*\n)(\s*-[^\n]*\n)+",
            lambda m: m.group(1) + f"    - {nick}\n",
            text, count=1,
        )
        changed.append(f"allowed_senders = [{nick}]")
    # owners (R6) — tambah blok bila belum ada
    if re.search(r"^\s*owners:", text, re.M):
        text = re.sub(r"(^\s*owners:[^\n]*\n)(\s*-[^\n]*\n)+",
                      lambda m: m.group(1) + f"    - {nick}\n", text, count=1, flags=re.M)
    else:
        text = re.sub(r"^(bot:\s*\n)", r"\1  owners:                     # R6, akses penuh\n    - " + nick + "\n",
                      text, count=1, flags=re.M)
    changed.append(f"owners = [{nick}] (R6)")

    # device.serial & resolusi (opsional)
    if args.port:
        text = re.sub(r"^(\s*serial:).*$", f"\g<1> 127.0.0.1:{args.port}", text, count=1, flags=re.M)
        changed.append(f"serial = 127.0.0.1:{args.port}")
    if args.width and args.height:
        text = re.sub(r"^(\s*width:).*$", f"\g<1> {args.width}", text, count=1, flags=re.M)
        text = re.sub(r"^(\s*height:).*$", f"\g<1> {args.height}", text, count=1, flags=re.M)
        changed.append(f"resolusi = {args.width}x{args.height}")

    path.write_text(text, encoding="utf-8")
    print(f"✔ {path} diperbarui:")
    for c in changed:
        print(f"   - {c}")

    # verifikasi hasil parse
    try:
        cfg2 = load_config(path)
        print(f"\n✔ config valid. Owner '{cfg2.get('bot.owner_nick')}' akan mendapat rank R6.")
    except Exception as exc:
        print(f"\n⚠️  config tidak valid setelah diubah: {exc}")
        return 1
    print("Langkah berikut: lmbot doctor")
    return 0


# --------------------------------------------------------------------------- #
# Subcommand: info (cara kerja bot, singkat)
# --------------------------------------------------------------------------- #
def cmd_info(args) -> int:  # noqa: C901
    from .about import AUTHOR, TAGLINE, VERSION
    from .imaging import EXPECTED_TEMPLATES, list_templates
    from .config import load_config as _load

    cfg = _load(args.config)
    tdir = cfg.resolve_path(cfg.get("templates.dir", "assets/templates"))
    fdir = cfg.resolve_path(cfg.get("flows.dir", "config/flows"))
    from .flows import load_flows

    flows = load_flows(fdir)
    aktif = sorted(k for k, v in flows.items() if v.enabled)
    print(f"{C.cmd}LMBot v{VERSION}{C.end} — {TAGLINE}")
    print(f"Dibuat oleh {AUTHOR}\n")
    print("CARA KERJA (5 langkah):")
    print("  1. Sumber perintah  : terminal / file / webhook / chat_tail")
    print("  2. Parser           : teks -> perintah + argumen (lmbot/parser.py)")
    print("  3. Otorisasi        : whitelist + rank R1-R6 (lmbot/roles.py)")
    print("  4. Buku besar       : debit/credit + audit + refund (lmbot/state.py)")
    print("  5. Aksi di layar    : flow YAML -> screenshot/tap/ketik via ADB (lmbot/ops.py)")
    print()
    print(f"device   : {cfg.get('device.driver')} {cfg.get('device.serial')} "
          f"({cfg.get('device.width')}x{cfg.get('device.height')})")
    print(f"owner    : {cfg.get('bot.owner_nick')} (R6)")
    print(f"flow     : {len(flows)} terbaca, {len(aktif)} aktif")
    tstatus = list_templates(tdir)
    print(f"template : {sum(tstatus.values())}/{len(EXPECTED_TEMPLATES)} siap")
    print(f"bank     : {cfg.resolve_path(cfg.get('bank.path'))}")
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
    p_serve.add_argument("--web-port", type=int, default=0, help="dashboard status (mis. 8081)")
    p_serve.add_argument("--once", nargs="*", help="jalankan perintah lalu keluar")
    p_serve.set_defaults(func=cmd_serve)

    p_once = sub.add_parser("cmd", help="jalankan satu perintah")
    p_once.add_argument("text", nargs="+")
    p_once.add_argument("--sender", default=None)
    p_once.set_defaults(func=cmd_once)

    p_setup = sub.add_parser("setup", help="set nick owner/whitelist tanpa buka Notepad")
    p_setup.add_argument("--nick", default="", help='nick in-game, mis. "Arken Ega"')
    p_setup.add_argument("--port", type=int, default=0, help="port ADB MuMu (mis. 16384)")
    p_setup.add_argument("--width", type=int, default=0)
    p_setup.add_argument("--height", type=int, default=0)
    p_setup.set_defaults(func=cmd_setup)

    p_info = sub.add_parser("info", help="ringkasan cara kerja & status")
    p_info.set_defaults(func=cmd_info)

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

    p_tpl = sub.add_parser("template", help="buat/lihat template dari screenshot mentah")
    tsub = p_tpl.add_subparsers(dest="template_action", required=True)
    t_list = tsub.add_parser("list", help="cek template mana yang sudah ada")
    t_list.set_defaults(func=cmd_template)
    t_add = tsub.add_parser("add", help="crop screenshot -> template PNG")
    t_add.add_argument("--screen", required=True, help="screenshot PNG fullscreen")
    t_add.add_argument("--name", required=True, help="nama template (lihat: template list)")
    t_add.add_argument("--box", required=True, help="x,y,w,h fraksi (0..1) atau piksel")
    t_add.add_argument("--scale", type=float, default=1.0)
    t_add.add_argument("--max-width", type=int, default=0)
    t_add.add_argument("--color", action="store_true", help="simpan berwarna (default grayscale)")
    t_add.add_argument("--preview", action="store_true", help="simpan juga versi besar berwarna")
    t_add.set_defaults(func=cmd_template)

    p_ver = sub.add_parser("verify", help="uji template terhadap screenshot")
    p_ver.add_argument("--screen", default=None)
    p_ver.add_argument("--adb", action="store_true", help="ambil screenshot dari emulator")
    p_ver.add_argument("--out", default="logs/screen.png")
    p_ver.add_argument("--name", default=None)
    p_ver.add_argument("--threshold", type=float, default=0.86)
    p_ver.set_defaults(func=cmd_verify)

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
