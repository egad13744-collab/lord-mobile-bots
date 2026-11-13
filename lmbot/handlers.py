"""Handler semua perintah pada gambar.

Setiap handler menerima (cmd, ctx) dan mengembalikan `Result`. Handler hanya
berbicara dengan `ops` (operasi game) dan `bank` (state) — tidak pernah
menyentuh ADB/koordinat secara langsung. Itu sebabnya seluruh logika bisa
dites tanpa emulator (lihat tests/).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from .ops import GameOps, OpsError
from .parser import (
    Command,
    arg_amount,
    arg_coords,
    arg_duration,
    arg_flag,
    arg_nick,
    arg_rss_type,
    arg_state,
    rss_vector,
)
from .roles import RANK_LABEL
from .state import CODE_TO_KEY, RSS_KEYS, BankStore, InsufficientFunds
from .utils import ParseError, fmt_rss, human, normalize_nick

Handler = Callable[["Cmd", "Context"], "Result"]


@dataclass
class Result:
    ok: bool
    reply: str = ""
    error: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    silent: bool = False

    @classmethod
    def success(cls, reply: str = "", **data) -> "Result":
        return cls(True, reply=reply, data=data)

    @classmethod
    def fail(cls, error: str) -> "Result":
        return cls(False, error=error)


@dataclass
class Cmd:
    name: str
    args: Dict[str, Any]
    sender: str
    raw: str = ""
    rank: str = "R1"

    def get(self, key: str, default: Any = None) -> Any:
        return self.args.get(key, default)

    @classmethod
    def from_parsed(cls, parsed: Command, rank: str = "R1") -> "Cmd":
        return cls(parsed.name, dict(parsed.args), parsed.sender, parsed.raw, rank)


@dataclass
class Context:
    cfg: Any
    bank: BankStore
    ops: GameOps
    logger: Any = None
    now: float = field(default_factory=time.time)
    tap_pause: float = 0.0

    def log(self, msg: str) -> None:
        if self.logger:
            self.logger(msg)


class Handlers:
    """Registry nama perintah -> fungsi."""

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.bank = ctx.bank
        self.ops = ctx.ops
        self._map: Dict[str, Handler] = {}
        self._register()

    # ---------------------------------------------------------------- #
    @property
    def suffixes(self) -> Dict[str, int]:
        return {
            k: int(v) for k, v in (self.cfg.get("bank.amount_suffixes") or {"k": 1000, "m": 10**6, "b": 10**9}).items()
        }

    @property
    def ui_labels(self) -> Dict[str, str]:
        """Label tampilan per key rss: {'food': 'Food', ...}."""
        units = self.cfg.get("bank.rss_units") or {}
        labels: Dict[str, str] = {}
        for code, meta in units.items():
            meta = meta or {}
            key = meta.get("key") or CODE_TO_KEY.get(code, code.lower())
            labels[key] = meta.get("label", key.title())
        for key in RSS_KEYS:
            labels.setdefault(key, key.title())
        return labels

    @property
    def code_labels(self) -> Dict[str, str]:
        """Label tampilan per kode: {'F': 'Food', ...}."""
        units = self.cfg.get("bank.rss_units") or {}
        return {c: (units.get(c) or {}).get("label", c) for c in "FSWOG"}

    def register(self, *names: str) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            for name in names:
                self._map[name] = fn
            return fn
        return deco

    def dispatch(self, cmd: Cmd) -> Result:
        fn = self._map.get(cmd.name)
        if not fn:
            return Result.fail(f"perintah !{cmd.name} belum diimplementasikan")
        try:
            return fn(cmd, self.ctx)
        except (ParseError, InsufficientFunds, OpsError) as exc:
            return Result.fail(str(exc))
        except Exception as exc:  # pragma: no cover - jaring pengaman
            if self.ctx.logger:
                self.ctx.logger(f"ERROR {cmd.name}: {exc!r}")
            return Result.fail(f"internal error: {exc}")

    # ================================================================ #
    # GUILD
    # ================================================================ #
    def _register(self) -> None:
        self._map.update(
            {
                # GUILD -------------------------------------------------
                "guild": self.h_guild,
                "stats": self.h_stats,
                "stats_all": self.h_stats_all,
                "pstats": self.h_pstats,
                "stop": self.h_stop,
                "pos": self.h_pos,
                "shield": self.h_shield,
                "shield_deploy": self.h_shield_deploy,
                "relocate": self.h_relocate,
                "relocatekvk": self.h_relocatekvk,
                "relocate_rand": self.h_relocate_rand,
                "recall_all": self.h_recall_all,
                "buildspam": self.h_buildspam,
                "buildspam_stop": self.h_buildspam_stop,
                "hunt": self.h_hunt,
                "addtitle": self.h_addtitle,
                "deltitle": self.h_deltitle,
                "whitelist": self.h_whitelist,
                "blacklist": self.h_blacklist,
                "unwhitelist": self.h_unwhitelist,
                "unblacklist": self.h_unblacklist,
                "abort": self.h_abort,
                "quest": self.h_quest,
                "setgather": self.h_setgather,
                "migrate": self.h_migrate,
                "snowbeast": self.h_snowbeast,
                "members": self.h_members,
                "joingvg": self.h_joingvg,
                "leavegvg": self.h_leavegvg,
                "clearboard": self.h_clearboard,
                "gyphon": self.h_gyphon,
                "joincha": self.h_joincha,
                "leavecha": self.h_leavecha,
                "joinda": self.h_joinda,
                "leaveda": self.h_leaveda,
                # SEARCH ------------------------------------------------
                "findtile": self.h_findtile,
                "findtile_any": self.h_findtile_any,
                "findtilelocal": self.h_findtilelocal,
                "findmonster": self.h_findmonster,
                "findnest": self.h_findnest,
                "findtile_gems": self.h_findtile_gems,
                # BALANCE -----------------------------------------------
                "bal": self.h_bal,
                "adminbal": self.h_adminbal,
                "adminbal_member": self.h_adminbal_member,
                "adminbag": self.h_adminbag,
                "setbal": self.h_setbal,
                "transfer": self.h_transfer,
                # RSS ---------------------------------------------------
                "help": self.h_help,
                "top": self.h_top,
                "sync": self.h_sync,
                "alerts": self.h_alerts,
                "rss": self.h_rss,
                "donate": self.h_donate,
                "adminrss": self.h_adminrss,
            }
        )
        for word in ("food", "stone", "wood", "ore", "gold", "grain", "rock", "timber", "iron"):
            self._map[f"rss_{word}"] = self.h_rss_single

    # ---------------------------------------------------------------- #
    # helper
    # ---------------------------------------------------------------- #
    def _nick(self, raw: str) -> str:
        resolved = self.bank.roster.resolve(raw)
        return resolved or raw

    def _require_funds(self, nick: str, key: str, amount: int) -> None:
        bal = self.bank.balance(nick)
        if bal.get(key, 0) < amount:
            raise InsufficientFunds(
                f"saldo {self.ui_labels.get(key, key)} {nick} "
                f"hanya {human(bal.get(key, 0))}, diminta {human(amount)}"
            )

    def _max_transfer_guard(self, rss: Dict[str, int]) -> None:
        limit = int(self.cfg.get("safety.max_rss_per_transfer", 3_000_000))
        unit_limit = limit
        for key, amount in rss.items():
            if amount > unit_limit and not self.cfg.get("safety.allow_large_transfer", False):
                raise ParseError(
                    f"jumlah {human(amount)} melebihi batas aman {human(unit_limit)} per tipe. "
                    f"Ubah safety.max_rss_per_transfer bila memang disengaja."
                )

    def _confirm_guard(self, cmd: Cmd, label: str) -> Optional[Result]:
        """Konfirmasi 2 langkah untuk aksi berisiko.

        Pola: `!guild AYU` -> bot minta `!guild AYU confirm`.
        Berlaku bila bot.confirm_risky = true.
        """
        if not self.cfg.get("bot.confirm_risky", True):
            return None
        if cmd.get("confirm") is True:  # user sudah mengetik kata `confirm`
            return None
        args = {k: v for k, v in cmd.args.items() if k != "confirm"}
        contoh = " ".join(str(v) for v in args.values() if isinstance(v, str) and v)
        return Result(
            True,
            f"⚠️ Konfirmasi: {label}.\n"
            f"Ketik ulang dengan kata `confirm` di akhir:\n"
            f"!{cmd.name} {contoh} confirm".replace("  ", " "),
            data={"pending": True},
        )

    def _log_action(self, action: str, params: Optional[dict] = None, sender: str = "") -> None:
        self.ctx.log(f"[action] {action} {params or ''} oleh {sender or '-'}")
        self.ops.run_action(action, params or {})

    # ================================================================ #
    # GUILD
    # ================================================================ #
    def h_guild(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(arg_nick(cmd.args))
        pending = self._confirm_guard(cmd, f"pindahkan bank ke klan {nick}")
        if pending:
            return pending
        self._log_action("guild", {"nick": nick}, cmd.sender)
        return Result.success(
            f"🏰 Bank dipindahkan ke klan {nick}", action="guild", nick=nick
        )

    def h_stats(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("stats", {}, cmd.sender)
        recent = self.bank.recent(5)
        lines = ["📊 Report kill monster:"]
        if not recent:
            lines.append("belum ada aktivitas tercatat")
        for tx in recent:
            lines.append(f"• {tx.get('time','')} {tx.get('kind')} {tx.get('nick')}")
        return Result.success("\n".join(lines), action="stats")

    def h_stats_all(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("stats_all", {}, cmd.sender)
        total = self.bank.bank_total()
        return Result.success(
            f"🎁 Report hadiah box klan\nTotal tabungan bank: {fmt_rss(total, self.ui_labels)}",
            action="stats_all",
        )

    def h_pstats(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(arg_nick(cmd.args))
        self._log_action("pstats", {"nick": nick}, cmd.sender)
        bal = self.bank.balance(nick)
        return Result.success(
            f"📊 {nick}\n{fmt_rss(bal, self.ui_labels)}", action="pstats", nick=nick
        )

    def h_stop(self, cmd: Cmd, ctx: Context) -> Result:
        seconds = arg_duration(cmd.args)
        if seconds > 86400:
            return Result.fail("durasi maksimal 24 jam (86400 detik)")
        until = self.bank.freeze(seconds, cmd.sender)
        self._log_action("stop", {"seconds": seconds}, cmd.sender)
        jam = seconds / 3600
        return Result.success(
            f"⏸️ Bank dimatikan selama {human(seconds)} detik ({jam:.2f} jam). "
            f"Transfer ditolak sampai {time.strftime('%H:%M:%S', time.localtime(until))}.",
            action="stop", seconds=seconds,
        )

    def h_pos(self, cmd: Cmd, ctx: Context) -> Result:
        to_chat = arg_flag(cmd.args, "chat")
        self._log_action("pos", {"chat": to_chat}, cmd.sender)
        bal = self.bank.bank_total()
        msg = f"📍 Lokasi bank dikirim{' ke chat' if to_chat else ''}. Isi bank: {fmt_rss(bal, self.ui_labels)}"
        return Result.success(msg, action="pos")

    def h_shield(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("shield", {}, cmd.sender)
        frozen = self.bank.freeze_remaining()
        status = f"⏸️ dijeda {frozen} detik" if frozen else "▶️ aktif"
        return Result.success(f"🛡️ Status shield & pengiriman bank: {status}", action="shield")

    def h_shield_deploy(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("shield_deploy", {}, cmd.sender)
        return Result.success("🛡️ Shield bank diaktifkan", action="shield_deploy")

    def h_relocate(self, cmd: Cmd, ctx: Context) -> Result:
        x, y = arg_coords(cmd.args)
        pending = self._confirm_guard(cmd, f"pindahkan bank ke ({x}, {y})")
        if pending:
            return pending
        self._log_action("relocate", {"x": x, "y": y}, cmd.sender)
        return Result.success(f"🧭 Bank dipindahkan ke ({x}, {y})", action="relocate")

    def h_relocatekvk(self, cmd: Cmd, ctx: Context) -> Result:
        try:
            k = int(str(cmd.get("k")))
        except (TypeError, ValueError):
            return Result.fail("kode kvk harus angka, contoh !relocatekvk 2800")
        pending = self._confirm_guard(cmd, f"pindahkan bank acak di KD {k}")
        if pending:
            return pending
        self._log_action("relocatekvk", {"k": k}, cmd.sender)
        return Result.success(f"🧭 Bank dipindahkan acak di KD {k}", action="relocatekvk")

    def h_relocate_rand(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("relocate_rand", {}, cmd.sender)
        return Result.success("🧭 Bank dipindahkan acak di KD", action="relocate_rand")

    def h_recall_all(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("recall_all", {}, cmd.sender)
        return Result.success("↩️ Semua troop dipanggil pulang", action="recall_all")

    def h_buildspam(self, cmd: Cmd, ctx: Context) -> Result:
        try:
            count = int(str(cmd.get("count")))
            level = int(str(cmd.get("level")))
        except (TypeError, ValueError):
            return Result.fail("format: !buildspam (jumlah) (level), contoh !buildspam 40 1")
        if not (1 <= count <= 500 and 1 <= level <= 30):
            return Result.fail("jumlah 1-500 dan level 1-30")
        self._log_action("buildspam", {"count": count, "level": level}, cmd.sender)
        return Result.success(f"🔨 Spam jahat tangan {count}x level {level}", action="buildspam")

    def h_buildspam_stop(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("buildspam_stop", {}, cmd.sender)
        return Result.success("⏹️ Spam jahat tangan dihentikan", action="buildspam_stop")

    def h_hunt(self, cmd: Cmd, ctx: Context) -> Result:
        x, y = arg_coords(cmd.args)
        self._log_action("hunt", {"x": x, "y": y}, cmd.sender)
        return Result.success(f"🎯 Bank memburu monster di ({x}, {y})", action="hunt")

    def h_addtitle(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(str(cmd.get("nick") or ""))
        title = str(cmd.get("title") or "").strip()
        if not nick or not title:
            return Result.fail("format: !addtitle (nick) (gelar)")
        self.bank.meta.setdefault("titles", {})[normalize_nick(nick)] = title
        self.bank.save()
        self._log_action("addtitle", {"nick": nick, "title": title}, cmd.sender)
        return Result.success(f"🏅 Gelar '{title}' diberikan ke {nick}", action="addtitle")

    def h_deltitle(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(str(cmd.get("nick") or ""))
        titles = self.bank.meta.get("titles", {})
        if normalize_nick(nick) in titles:
            removed = titles.pop(normalize_nick(nick))
            self.bank.save()
            self._log_action("deltitle", {"nick": nick}, cmd.sender)
            return Result.success(f"🗑️ Gelar '{removed}' dihapus dari {nick}", action="deltitle")
        return Result.fail(f"{nick} tidak punya gelar tercatat")

    def h_whitelist(self, cmd: Cmd, ctx: Context) -> Result:
        nick = str(cmd.get("nick") or "").strip()
        rank = str(cmd.get("rank") or "R1").upper()
        if not nick:
            return Result.fail("format: !whitelist (nick)(rank)")
        if not rank.startswith("R") or rank not in RANK_LABEL:
            return Result.fail("rank harus R1-R5")
        if rank == "R6":
            return Result.fail("R6 hanya untuk owner (pakai file state)")
        self.bank.roster.set_member(nick, rank)
        self.bank.save()
        self._log_action("whitelist", {"nick": nick, "rank": rank}, cmd.sender)
        return Result.success(
            f"✅ {nick} masuk whitelist sebagai {RANK_LABEL[rank]}", action="whitelist"
        )

    def h_blacklist(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(arg_nick(cmd.args))
        self.bank.roster.blacklist_add(nick)
        self.bank.save()
        self._log_action("blacklist", {"nick": nick}, cmd.sender)
        return Result.success(f"🚫 {nick} masuk blacklist", action="blacklist")

    def h_unwhitelist(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(arg_nick(cmd.args))
        if self.bank.roster.remove_member(nick):
            self.bank.save()
            self._log_action("unwhitelist", {"nick": nick}, cmd.sender)
            return Result.success(f"➖ {nick} dihapus dari whitelist", action="unwhitelist")
        return Result.fail(f"{nick} tidak ada di whitelist")

    def h_unblacklist(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(arg_nick(cmd.args))
        if self.bank.roster.blacklist_remove(nick):
            self.bank.save()
            self._log_action("unblacklist", {"nick": nick}, cmd.sender)
            return Result.success(f"✅ {nick} dihapus dari blacklist", action="unblacklist")
        return Result.fail(f"{nick} tidak ada di blacklist")

    def h_abort(self, cmd: Cmd, ctx: Context) -> Result:
        self.bank.freeze(600, cmd.sender)  # jaring pengaman 10 menit
        self._log_action("abort", {}, cmd.sender)
        return Result.success("🛑 Semua pengiriman RSS dibatalkan (bank dijeda 10 menit)", action="abort")

    def h_quest(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("quest", {}, cmd.sender)
        return Result.success("🧩 Cek misi GF bank — lihat panel misi di game", action="quest")

    def h_setgather(self, cmd: Cmd, ctx: Context) -> Result:
        state = arg_state(cmd.args)
        self.bank.meta["gather_enabled"] = state
        self.bank.save()
        self._log_action("setgather", {"state": state}, cmd.sender)
        return Result.success(
            f"⛏️ Bot menambang {'diaktifkan' if state else 'dinonaktifkan'}", action="setgather"
        )

    def h_migrate(self, cmd: Cmd, ctx: Context) -> Result:
        try:
            k, x, y = int(str(cmd.get("k"))), int(str(cmd.get("x"))), int(str(cmd.get("y")))
        except (TypeError, ValueError):
            return Result.fail("format: !migrate (k) (x) (y), contoh !migrate 123 4 5")
        pending = self._confirm_guard(cmd, f"migrasi bank ke KD {k} ({x}, {y})")
        if pending:
            return pending
        self._log_action("migrate", {"k": k, "x": x, "y": y}, cmd.sender)
        return Result.success(f"🚚 Bank dimigrasi ke KD {k} ({x}, {y})", action="migrate")

    def h_snowbeast(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("snowbeast", {}, cmd.sender)
        return Result.success("❄️ Familiar snowbeast diaktifkan", action="snowbeast")

    def h_members(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("members", {}, cmd.sender)
        roster = self.bank.roster
        lines = [f"👥 Whitelist ({len(roster.whitelist)}):"]
        for nick, rank in sorted(roster.whitelist.items()):
            lines.append(f"• {nick} — {rank}")
        if roster.blacklist:
            lines.append(f"🚫 Blacklist: {', '.join(sorted(roster.blacklist))}")
        if len(lines) == 1:
            lines.append("(kosong)")
        return Result.success("\n".join(lines), action="members")

    def h_joingvg(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("joingvg", {}, cmd.sender)
        return Result.success("⚔️ Bank masuk arena GE", action="joingvg")

    def h_leavegvg(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("leavegvg", {}, cmd.sender)
        return Result.success("🏳️ Bank keluar dari arena GE", action="leavegvg")

    def h_clearboard(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("clearboard", {}, cmd.sender)
        return Result.success("🧹 Seluruh papan misi dihapus", action="clearboard")

    def h_gyphon(self, cmd: Cmd, ctx: Context) -> Result:
        self._log_action("gyphon", {}, cmd.sender)
        return Result.success("🐦 Pasukan ditarik cepat (gyphon)", action="gyphon")

    def _arena(self, cmd: Cmd, arena: str, enter: bool) -> Result:
        code = str(cmd.get("arena") or "").strip()
        use_f = arg_flag(cmd.args, "f")
        if enter and not code:
            return Result.fail(f"format: !{'joincha' if arena=='chaos' else 'joinda'} (kode arena)")
        params = {"arena": arena, "code": code, "f": use_f}
        self._log_action("joincha" if arena == "chaos" and enter else
                         "leavecha" if arena == "chaos" else
                         "joinda" if enter else "leaveda", params, cmd.sender)
        if enter:
            extra = " (mode F)" if use_f else ""
            return Result.success(f"🌀 Masuk arena {arena} kode {code}{extra}", action="join")
        return Result.success(f"🚪 Keluar dari arena {arena}", action="leave")

    def h_joincha(self, cmd: Cmd, ctx: Context) -> Result:
        return self._arena(cmd, "chaos", True)

    def h_leavecha(self, cmd: Cmd, ctx: Context) -> Result:
        return self._arena(cmd, "chaos", False)

    def h_joinda(self, cmd: Cmd, ctx: Context) -> Result:
        return self._arena(cmd, "DA", True)

    def h_leaveda(self, cmd: Cmd, ctx: Context) -> Result:
        return self._arena(cmd, "DA", False)

    # ================================================================ #
    # SEARCH
    # ================================================================ #
    _TILE_TYPES = {
        "food": "food", "stone": "stone", "wood": "wood", "ore": "ore", "gold": "gold",
        "f": "food", "s": "stone", "w": "wood", "o": "ore", "g": "gold",
        "gems": "gems", "gem": "gems",
        "any": "any", "semua": "any",
    }

    def _tile(self, cmd: Cmd, local: bool = False, any_type: bool = False) -> Result:
        raw = "any" if any_type else str(cmd.get("type") or cmd.get("any") or "").lower()
        tile = self._TILE_TYPES.get(raw)
        if not tile:
            return Result.fail(
                "tipe tambang: food/stone/wood/ore/gold/gems/any"
            )
        try:
            level = int(str(cmd.get("level")))
        except (TypeError, ValueError):
            return Result.fail("level harus angka 1-5")
        if not 1 <= level <= 5:
            return Result.fail("level tambang 1-5")
        chat = arg_flag(cmd.args, "chat")
        action = "findtilelocal" if local else "findtile"
        self._log_action(action, {"type": tile, "level": level, "chat": chat}, cmd.sender)
        where = "di sekitar member" if local else "di sekitar bank"
        return Result.success(
            f"🔍 Mencari tambang {tile} level {level} {where}"
            f"{' (kirim ke chat)' if chat else ''}",
            action=action,
        )

    def h_findtile(self, cmd: Cmd, ctx: Context) -> Result:
        return self._tile(cmd)

    def h_findtile_any(self, cmd: Cmd, ctx: Context) -> Result:
        return self._tile(cmd, any_type=True)

    def h_findtilelocal(self, cmd: Cmd, ctx: Context) -> Result:
        return self._tile(cmd, local=True)

    def h_findtile_gems(self, cmd: Cmd, ctx: Context) -> Result:
        cmd.args["type"] = "gems"
        return self._tile(cmd)

    def h_findmonster(self, cmd: Cmd, ctx: Context) -> Result:
        monster = str(cmd.get("monster") or "").strip().lower()
        if not monster:
            return Result.fail("format: !findmonster (nama) (level), contoh !findmonster blackwing 2")
        try:
            level = int(str(cmd.get("level")))
        except (TypeError, ValueError):
            return Result.fail("level monster harus angka")
        chat = arg_flag(cmd.args, "chat")
        self._log_action("findmonster", {"monster": monster, "level": level, "chat": chat}, cmd.sender)
        return Result.success(
            f"🎯 Mencari monster {monster} level {level}{' (kirim ke chat)' if chat else ''}",
            action="findmonster",
        )

    def h_findnest(self, cmd: Cmd, ctx: Context) -> Result:
        try:
            level = int(str(cmd.get("level")))
        except (TypeError, ValueError):
            return Result.fail("format: !findnest (level), contoh !findnest 4 chat")
        chat = arg_flag(cmd.args, "chat")
        self._log_action("findnest", {"level": level, "chat": chat}, cmd.sender)
        return Result.success(
            f"🌑 Mencari darkness level {level}{' (kirim ke chat)' if chat else ''}", action="findnest"
        )

    # ================================================================ #
    # BALANCE
    # ================================================================ #
    def h_bal(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(cmd.sender)
        bal = self.bank.balance(nick)
        return Result.success(
            f"💰 Saldo {nick} di bank:\n{fmt_rss(bal, self.ui_labels)}"
            + (f"\n⏸️ Bank dijeda {self.bank.freeze_remaining()} detik" if self.bank.is_frozen() else ""),
            nick=nick, balance=bal,
        )

    def h_adminbal(self, cmd: Cmd, ctx: Context) -> Result:
        if str(cmd.get("nick") or "").strip():
            return self.h_adminbal_member(cmd, ctx)
        total = self.bank.bank_total()
        self._log_action("adminbal", {}, cmd.sender)
        return Result.success(
            f"📦 RSS di luar tas bank (total semua member):\n{fmt_rss(total, self.ui_labels)}",
            total=total,
        )

    def h_adminbal_member(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(arg_nick(cmd.args))
        bal = self.bank.balance(nick)
        return Result.success(
            f"📦 Tabungan {nick}:\n{fmt_rss(bal, self.ui_labels)}", nick=nick, balance=bal
        )

    def h_adminbag(self, cmd: Cmd, ctx: Context) -> Result:
        total = self.bank.bank_total()
        self._log_action("adminbag", {}, cmd.sender)
        return Result.success(
            f"🎒 RSS di dalam tas bank:\n{fmt_rss(total, self.ui_labels)}", total=total
        )

    def h_setbal(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(arg_nick(cmd.args))
        code = arg_rss_type(cmd.args, "type")
        amount = arg_amount(cmd.args, "amount", self.suffixes)
        limit = int(self.cfg.get("safety.max_balance_per_command", 100_000_000))
        if amount > limit:
            return Result.fail(f"nilai melebihi batas aman {human(limit)}")
        key = CODE_TO_KEY[code]
        bal = self.bank.balance(nick)
        bal[key] = amount
        new = self.bank.set_balance(nick, bal, cmd.sender)
        self._log_action("setbal", {"nick": nick, "type": key, "amount": amount}, cmd.sender)
        return Result.success(
            f"✏️ Saldo {self.code_labels[code]} {nick} diset ke {human(amount)}\n"
            f"Saldo sekarang: {fmt_rss(new, self.ui_labels)}",
            action="setbal",
        )

    def h_transfer(self, cmd: Cmd, ctx: Context) -> Result:
        sender_nick = self._nick(cmd.sender)
        target = self._nick(arg_nick(cmd.args))
        code = arg_rss_type(cmd.args, "type")
        amount = arg_amount(cmd.args, "amount", self.suffixes)
        key = CODE_TO_KEY[code]
        if normalize_nick(sender_nick) == normalize_nick(target):
            return Result.fail("tidak bisa transfer ke diri sendiri")
        if self.bank.is_frozen():
            return Result.fail(
                f"bank sedang dijeda {self.bank.freeze_remaining()} detik "
                f"(gunakan !shield untuk cek, atau tunggu)"
            )
        self._max_transfer_guard({key: amount})
        self._require_funds(sender_nick, key, amount)
        # 1) kurangi saldo pengirim, 2) kirim di game, 3) refund bila gagal
        self.bank.debit(sender_nick, {key: amount}, note=f"transfer ke {target}", actor=cmd.sender)
        try:
            self.ops.open_bank_panel(target)
            self.ops.send_rss_to_member(target, {key: amount})
        except OpsError as exc:
            self.bank.credit(sender_nick, {key: amount}, note="refund gagal kirim", actor="system")
            return Result.fail(f"gagal mengirim di game, saldo dikembalikan: {exc}")
        # RSS sudah diterima target di game -> catat juga di buku besar
        self.bank.credit(target, {key: amount}, note=f"transfer dari {sender_nick}", actor=cmd.sender)
        new_bal = self.bank.balance(sender_nick)
        self.ctx.log(f"[transfer] {sender_nick} -> {target} {key} {amount}")
        return Result.success(
            f"✅ Transfer {self.code_labels[code]} {human(amount)} ke {target} berhasil\n"
            f"Sisa saldo {sender_nick}: {human(new_bal.get(key, 0))}",
            action="transfer", nick=target, amount=amount, balance=new_bal,
        )

    # ================================================================ #
    # RSS
    # ================================================================ #
    def _send_vector(self, cmd: Cmd, nick: str, vec: Dict[str, int], action: str) -> Result:
        if self.bank.is_frozen():
            return Result.fail(
                f"bank sedang dijeda {self.bank.freeze_remaining()} detik (perintah !stop/!abort)"
            )
        amounts = {CODE_TO_KEY[c]: v for c, v in vec.items() if v > 0}
        if not amounts:
            return Result.fail("semua jumlah 0, tidak ada yang dikirim")
        self._max_transfer_guard(amounts)
        for key, amount in amounts.items():
            self._require_funds(nick, key, amount)
        # debit dulu (atomic di store), lalu kirim; refund bila ops gagal
        self.bank.debit(nick, amounts, note=action, actor=cmd.sender)
        try:
            self.ops.open_bank_panel(nick)
            self.ops.send_rss_to_member(nick, amounts)
        except OpsError as exc:
            self.bank.credit(nick, amounts, note="refund gagal kirim", actor="system")
            return Result.fail(f"gagal mengirim di game, saldo dikembalikan: {exc}")
        return Result.success(
            f"✅ Terkirim ke {nick}: {fmt_rss(amounts, self.ui_labels)}\n"
            f"Sisa saldo: {fmt_rss(self.bank.balance(nick), self.ui_labels)}",
            action=action, nick=nick, sent=amounts,
        )

    def h_rss(self, cmd: Cmd, ctx: Context) -> Result:
        nick = self._nick(cmd.sender)
        vec = rss_vector(cmd.args, self.suffixes)
        return self._send_vector(cmd, nick, vec, "rss")

    def h_rss_single(self, cmd: Cmd, ctx: Context) -> Result:
        from .parser import RSS_SHORTCUT_TYPES

        nick = self._nick(cmd.sender)
        word = cmd.name.split("_", 1)[1] if "_" in cmd.name else ""
        code = RSS_SHORTCUT_TYPES.get(word)
        if not code:
            matches = [c for w, c in RSS_SHORTCUT_TYPES.items() if w in cmd.args]
            if not matches:
                return Result.fail("tipe rss tidak dikenal")
            code = matches[0]
        amount = arg_amount(cmd.args, "amount", self.suffixes)
        vec = {c: 0 for c in "FSWOG"}
        vec[code] = amount
        return self._send_vector(cmd, nick, vec, f"rss_{code.lower()}")

    def h_donate(self, cmd: Cmd, ctx: Context) -> Result:
        target = self._nick(arg_nick(cmd.args))
        code = arg_rss_type(cmd.args, "type")
        amount = arg_amount(cmd.args, "amount", self.suffixes)
        sender_nick = self._nick(cmd.sender)
        key = CODE_TO_KEY[code]
        if self.bank.is_frozen():
            return Result.fail(f"bank sedang dijeda {self.bank.freeze_remaining()} detik")
        self._max_transfer_guard({key: amount})
        self._require_funds(sender_nick, key, amount)
        self.bank.debit(sender_nick, {key: amount}, note=f"donate ke {target}", actor=cmd.sender)
        try:
            self.ops.open_bank_panel(target)
            self.ops.send_rss_to_member(target, {key: amount})
        except OpsError as exc:
            self.bank.credit(sender_nick, {key: amount}, note="refund gagal kirim", actor="system")
            return Result.fail(f"gagal mengirim di game, saldo dikembalikan: {exc}")
        self.bank.credit(target, {key: amount}, note=f"donasi dari {sender_nick}", actor=cmd.sender)
        return Result.success(
            f"🎁 Donasi {self.code_labels[code]} {human(amount)} untuk {target} terkirim",
            action="donate", nick=target, amount=amount,
        )

    def h_adminrss(self, cmd: Cmd, ctx: Context) -> Result:
        target = self._nick(arg_nick(cmd.args))
        vec = rss_vector(cmd.args, self.suffixes)
        return self._send_vector(cmd, target, vec, "adminrss")


    # ================================================================ #
    # INFO
    # ================================================================ #
    def h_help(self, cmd: Cmd, ctx: Context) -> Result:
        return Result.success(help_text(self.cfg, str(cmd.get("category") or "").strip() or None))

    def h_top(self, cmd: Cmd, ctx: Context) -> Result:
        raw = str(cmd.get("key") or "food").strip().lower()
        key = CODE_TO_KEY.get(raw.upper(), raw)
        if key not in RSS_KEYS:
            return Result.fail("key harus food/stone/wood/ore/gold")
        rows = self.bank.leaderboard(key, limit=5)
        if not rows:
            return Result.success(f"📊 Belum ada saldo {key} tercatat")
        lines = [f"🏆 Top 5 {self.ui_labels[key]}:"]
        for i, (nick, val) in enumerate(rows, 1):
            lines.append(f"{i}. {nick} — {human(val)}")
        return Result.success("\n".join(lines), key=key)

    def h_sync(self, cmd: Cmd, ctx: Context) -> Result:
        total = self.bank.bank_total()
        self._log_action("adminbag", {}, cmd.sender)
        return Result.success(
            "🔄 Sinkronisasi:\n"
            f"• Saldo tercatat: {fmt_rss(total, self.ui_labels)}\n"
            "• Isi tas bank di game belum dibaca otomatis (butuh OCR, opsional).\n"
            "Bandingkan dengan !adminbag lalu koreksi lewat !setbal bila perlu.",
            total=total,
        )

    def h_alerts(self, cmd: Cmd, ctx: Context) -> Result:
        sink = getattr(self.ops, "alerts", None)
        rows = sink.recent(5) if sink else []
        if not rows:
            return Result.success("✅ Tidak ada peringatan terbaru")
        lines = ["⚠️ Peringatan terakhir:"]
        for r in rows:
            lines.append(f"• {r.get('time','')} [{r.get('level')}] {r.get('title')}")
        return Result.success("\n".join(lines))


# --------------------------------------------------------------------------- #
def build_handlers(ctx: Context) -> Handlers:
    return Handlers(ctx)


def help_text(cfg, category: Optional[str] = None) -> str:
    from .parser import iter_specs

    order = ["GUILD", "SEARCH", "BALANCE", "RSS"]
    cats = [category.upper()] if category else order
    parts = []
    for cat in cats:
        specs = [s for s in iter_specs(cat) if not s.name.startswith("rss_")]
        if not specs:
            continue
        parts.append(f"━━ {cat} ━━")
        for s in specs:
            rank = f" [{s.min_rank}+]" if s.min_rank != "R1" else ""
            parts.append(f"!{s.pattern:<34} {s.description}{rank}")
    parts.append("")
    parts.append("RSS singkat: !food 100m, !stone 50m, !wood 50m, !ore 50m, !gold 50m")
    parts.append("Keterangan: F=food, S=stone, W=wood, O=ore, G=gold (maks 5 komponen)")
    return "\n".join(parts)
