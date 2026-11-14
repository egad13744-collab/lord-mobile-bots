"""Parser perintah chat -> objek Command.

Semua kode pada gambar didaftarkan di SPECS. Parser bersifat murni (tanpa I/O)
sehingga mudah diuji dan dipakai ulang oleh CLI, chat source, maupun webhook.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .utils import ParseError, parse_amount, parse_duration, parse_rss_vector


@dataclass(frozen=True)
class CommandSpec:
    name: str
    pattern: str
    category: str
    usage: str
    description: str
    example: str = ""
    min_rank: str = "R1"
    risky: bool = False
    params: Tuple[str, ...] = ()

    @property
    def tokens(self) -> List[str]:
        return self.pattern.split()


@dataclass
class Command:
    spec: CommandSpec
    raw: str
    args: Dict[str, object] = field(default_factory=dict)
    sender: str = ""

    @property
    def name(self) -> str:
        return self.spec.name

    def __repr__(self) -> str:  # pragma: no cover
        return f"Command({self.name}, {self.args})"


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def _s(name, pattern, category, usage, description, example="", **kw) -> CommandSpec:
    params = tuple(m.group(1) for m in re.finditer(r"<(\w+)\??>", pattern))
    return CommandSpec(
        name=name,
        pattern=pattern,
        category=category,
        usage=usage,
        description=description,
        example=example,
        params=params,
        **kw,
    )


SPECS: List[CommandSpec] = []

# ---------------------------------- GUILD ---------------------------------- #
SPECS += [
    _s("guild", "guild <nick> ?confirm", "GUILD", "!guild (nick klan)",
       "memindahkan bank klan ke klan yang dituju", "!guild AYU", min_rank="R4", risky=True),
    _s("stats", "stats", "GUILD", "!stats", "melihat report kill monster", "!stats"),
    _s("stats_all", "stats all", "GUILD", "!stats all", "melihat report hadiah box klan", "!stats all"),
    _s("pstats", "pstats <nick>", "GUILD", "!pstats nick",
       "melihat report kill monster anggota", "!pstats arken_ega"),
    _s("stop", "stop <duration>", "GUILD", "!stop (waktu detik)",
       "mengoffkan bank dalam waktu yang diminta", "!stop 3600",
       min_rank="R4", risky=True),
    _s("pos", "pos ?chat", "GUILD", "!pos", "mengirim lokasi bank", "!pos / !pos chat"),
    _s("shield", "shield", "GUILD", "!shield", "cek waktu shield bank", "!shield"),
    _s("shield_deploy", "shield deploy", "GUILD", "!shield deploy",
       "mengaktifkan shield bank", "!shield deploy", min_rank="R4", risky=True),
    _s("relocate", "relocate <x> <y> ?confirm", "GUILD", "!relocate (X)(Y)",
       "memindahkan bank ke koordinat yang diminta", "!relocate 123 456",
       min_rank="R4", risky=True),
    _s("relocatekvk", "relocatekvk <k> ?confirm", "GUILD", "!relocatekvk (K)",
       "memindahkan bank secara acak ke kd kvk", "!relocatekvk 2800",
       min_rank="R4", risky=True),
    _s("relocate_rand", "relocate rand", "GUILD", "!relocate rand",
       "memindahkan bank secara acak di kd", "!relocate rand", min_rank="R4", risky=True),
    _s("recall_all", "recall all", "GUILD", "!recall all",
       "menggulung pulang troop dari luar kastil", "!recall all", min_rank="R4"),
    _s("buildspam", "buildspam <count> <level>", "GUILD", "!buildspam",
       "spam jahat tangan (jt)", "!buildspam 40 1", min_rank="R3"),
    _s("buildspam_stop", "buildspam stop", "GUILD", "!buildspam stop",
       "menghentikan spam jahat tangan (jt)", "!buildspam stop", min_rank="R3"),
    _s("hunt", "hunt <x> <y>", "GUILD", "!hunt (X)(Y)",
       "bank memburu monster sesuai target", "!hunt 123 456", min_rank="R3"),
    _s("addtitle", "addtitle <nick> <title>", "GUILD", "!addtitle",
       "memberikan gelar yang telah diberikan", "!addtitle arken_ega chief", min_rank="R4"),
    _s("deltitle", "deltitle <nick>", "GUILD", "!deltitle",
       "menghapus gelar yang telah diberikan", "!deltitle chief", min_rank="R4"),
    _s("whitelist", "whitelist <nick> <rank>", "GUILD", "!whitelist (nick)(rank)",
       "auto acc dan auto up rank member", "!whitelist arken_ega R3", min_rank="R5"),
    _s("blacklist", "blacklist <nick>", "GUILD", "!blacklist (nick)",
       "menolak member yang mendaftar ke klan", "!blacklist arken_ega", min_rank="R4"),
    _s("unwhitelist", "unwhitelist <nick>", "GUILD", "!unwhitelist (nick)",
       "menghapus member dari daftar whitelist", "!unwhitelist arken_ega", min_rank="R5"),
    _s("unblacklist", "unblacklist <nick>", "GUILD", "!unblacklist (nick)",
       "menghapus member dari daftar blacklist", "!unblacklist arken_ega", min_rank="R4"),
    _s("abort", "abort", "GUILD", "!abort", "membatalkan semua pengiriman rss", "!abort",
       min_rank="R4"),
    _s("quest", "quest", "GUILD", "!quest", "cek misi GF bank", "!quest"),
    _s("setgather", "setgather <state>", "GUILD", "!setgather (on/off)",
       "mengaktifkan/menonaktifkan bot menambang", "!setgather on", min_rank="R4"),
    _s("migrate", "migrate <k> <x> <y> ?confirm", "GUILD", "!migrate k x y",
       "untuk memindahkan bank ke kd lain", "!migrate 123 4 5", min_rank="R5", risky=True),
    _s("snowbeast", "snowbeast", "GUILD", "!snowbeast",
       "mengaktifkan familiar snowbeast", "!snowbeast", min_rank="R4"),
    _s("members", "members", "GUILD", "!members", "refresh daftar member klan", "!members"),
    _s("joingvg", "joingvg", "GUILD", "!joingvg", "memindahkan bank ke arena GE", "!joingvg",
       min_rank="R4", risky=True),
    _s("leavegvg", "leavegvg", "GUILD", "!leavegvg", "mengeluarkan bank dari arena GE", "!leavegvg",
       min_rank="R4", risky=True),
    _s("clearboard", "clearboard", "GUILD", "!clearboard",
       "untuk menghapus seluruh papan misi", "!clearboard", min_rank="R4"),
    _s("gyphon", "gyphon", "GUILD", "!gyphon", "menarik cepat pasukan (familiar aktif)", "!gyphon",
       min_rank="R3"),
    _s("joincha", "joincha <arena> ?f", "GUILD", "!joinca (kode arena)",
       "untuk masuk ke arena chaos", "!joinca 1 F", min_rank="R4", risky=True),
    _s("joincha", "joinca <arena> ?f", "GUILD", "!joinca (kode arena)",
       "untuk masuk ke arena chaos", "!joinca 1 F", min_rank="R4", risky=True),
    _s("leavecha", "leavecha", "GUILD", "!leaveca", "untuk keluar dari arena chaos", "!leaveca",
       min_rank="R4"),
    _s("leavecha", "leaveca", "GUILD", "!leaveca", "untuk keluar dari arena chaos", "!leaveca",
       min_rank="R4"),
    _s("joinda", "joinda", "GUILD", "!joinda", "untuk masuk ke arena DA", "!joinda",
       min_rank="R4", risky=True),
    _s("leaveda", "leaveda", "GUILD", "!leaveda", "untuk keluar dari arena DA", "!leaveda",
       min_rank="R4"),
]

# ---------------------------------- SEARCH --------------------------------- #
SPECS += [
    _s("findtile", "findtile <type> <level> ?chat", "SEARCH", "!findtile (type)(level)",
       "mencari tambang disekitar bank", "!findtile food 4 chat"),
    _s("findtile_any", "findtile any <level> ?chat", "SEARCH", "!findtile (any) (level)",
       "mencari semua jenis tambang disekitar bank", "!findtile any 4 chat"),
    _s("findtilelocal", "findtilelocal <type> <level> ?chat", "SEARCH",
       "!findtilelocal (type)(level)", "mencari tambang yang member perintah",
       "!findtilelocal food 4 chat"),
    _s("findmonster", "findmonster <monster> <level> ?chat", "SEARCH", "!findmonster (nama)(level)",
       "mencari monster", "!findmonster blackwing 2 chat"),
    _s("findnest", "findnest <level> ?chat", "SEARCH", "!findnest (level)",
       "mencari darkness", "!findnest 4 chat"),
    _s("findtile_gems", "findtile gems <level> ?chat", "SEARCH", "!findtile gems (level)",
       "mencari tambang gems", "!findtile gems 4 chat"),
]

# --------------------------------- BALANCE --------------------------------- #
SPECS += [
    _s("bal", "bal", "BALANCE", "!bal", "cek tabungan di bank", "!bal"),
    _s("adminbal", "adminbal", "BALANCE", "!adminbal", "cek jumlah rss di luar tas bank", "!adminbal",
       min_rank="R4"),
    _s("adminbal_member", "adminbal <nick>", "BALANCE", "!adminbal (nick)",
       "cek tabungan member yang menabung di bank", "!adminbal arken_ega", min_rank="R4"),
    _s("adminbag", "adminbag", "BALANCE", "!adminbag", "cek jumlah rss di dalam tas", "!adminbag",
       min_rank="R4"),
    _s("setbal", "setbal <nick> <type> <amount>", "BALANCE", "!setbal",
       "menetapkan saldo secara manual ke akun member", "!setbal arken_ega food 100m",
       min_rank="R5", risky=True),
    _s("transfer", "transfer <nick> <type> <amount>", "BALANCE", "!transfer (nick)(type)(jumlah)",
       "mentransfer saldo tabungan ke member lain", "!transfer arken_ega ore 100m", risky=True),
]

# ----------------------------------- RSS ----------------------------------- #
SPECS += [
    _s("rss", "rss <f> <s> <w> <o> <g>", "RSS", "!rss (F)(S)(W)(O)(G)",
       "mengirimkan semua tipe rss yang diminta", "!rss 5m 5m 5m 5m 5m", risky=True),
    _s("donate", "donate <type> <nick> <amount>", "RSS", "!donate (type)(nick)(jumlah)",
       "mengirimkan rss ke player yang dituju", "!donate food arken_ega 100m", risky=True),
    _s("adminrss", "adminrss <f> <s> <w> <o> <g> <nick>", "RSS", "!adminrss",
       "mengirimkan semua tipe rss ke player yang dituju (hanya admin)",
       "!adminrss 1m 0 0 0 0 arken_ega", min_rank="R5", risky=True),
]

# ----------------------------------- INFO ---------------------------------- #
SPECS += [
    _s("help", "help <category?>", "INFO", "!help",
       "daftar perintah yang tersedia", "!help / !help RSS"),
    _s("top", "top <key?>", "INFO", "!top (food/stone/wood/ore/gold)",
       "peringkat penabung terbesar", "!top food"),
    _s("sync", "sync", "INFO", "!sync",
       "cek selisih saldo tercatat dengan isi tas bank", "!sync"),
    _s("alerts", "alerts", "INFO", "!alerts",
       "peringatan terakhir dari bot", "!alerts", min_rank="R4"),
    _s("version", "version", "INFO", "!version",
       "versi bot & pembuatnya", "!version"),
]

# ------------------------- OPERASIONAL (premium) --------------------------- #
SPECS += [
    _s("queue", "queue", "OPS", "!queue", "melihat antrian pengiriman yang menunggu", "!queue"),
    _s("jobs", "jobs", "OPS", "!jobs", "riwayat pekerjaan antrian terakhir", "!jobs", min_rank="R4"),
    _s("cancel", "cancel <id>", "OPS", "!cancel (id)", "membatalkan job di antrian", "!cancel 12",
       min_rank="R4"),
    _s("retry", "retry <id>", "OPS", "!retry (id)", "mengulang job yang gagal", "!retry 12",
       min_rank="R4"),
    _s("cron", "cron <action>", "OPS", "!cron list|add|del",
       "jadwal otomatis (list, add \"0 2 * * *\" !top food, del 1)", "!cron list", min_rank="R5"),
    _s("quota", "quota", "OPS", "!quota", "sisa kuota harian kamu", "!quota"),
    _s("audit", "audit <action?>", "OPS", "!audit verify|log",
       "cek keutuhan rantai audit & log transaksi", "!audit verify", min_rank="R4"),
    _s("undo", "undo", "OPS", "!undo", "membatalkan transaksi terakhir", "!undo", min_rank="R5",
       risky=True),
    _s("backup", "backup", "OPS", "!backup", "membuat backup state sekarang", "!backup",
       min_rank="R4"),
]

# Dynamic: !food 100m, !ore 50m, dst. (lihat build_rss_shortcuts)
RSS_SHORTCUT_TYPES = {
    "food": "F", "stone": "S", "wood": "W", "ore": "O", "gold": "G",
    # alias umum di game
    "grain": "F", "rock": "S", "timber": "W", "iron": "O",
}

RISKY_NAMES = {s.name for s in SPECS if s.risky}


def build_rss_shortcuts(units: Optional[dict] = None) -> List[CommandSpec]:
    specs = []
    for word, code in RSS_SHORTCUT_TYPES.items():
        specs.append(
            _s(
                f"rss_{word}",
                f"{word} <amount>",
                "RSS",
                f"!{word} jumlah",
                f"mengirimkan tipe rss tertentu yang diminta ({code})",
                f"!{word} 100m",
            )
        )
    return specs


ALL_SPECS: List[CommandSpec] = SPECS + build_rss_shortcuts()


def _literal_prefix(spec: CommandSpec) -> Tuple[str, ...]:
    """Token literal di awal pola, berhenti di token parameter/opsional."""
    out = []
    for tok in spec.tokens:
        if tok.startswith("<") or tok.startswith("?"):
            break
        out.append(tok.lower())
    return tuple(out)


_INDEX: Dict[Tuple[str, ...], List[CommandSpec]] = {}
for _spec in ALL_SPECS:
    _INDEX.setdefault(_literal_prefix(_spec), []).append(_spec)
_MAX_PREFIX = max(len(k) for k in _INDEX)
_MAX_TOKENS = max(len(s.tokens) for s in ALL_SPECS)


# --------------------------------------------------------------------------- #
# Index & parse
# --------------------------------------------------------------------------- #
class UnknownCommand(Exception):
    def __init__(self, text: str, suggestion: str = ""):
        self.text = text
        self.suggestion = suggestion
        msg = f"perintah tidak dikenal: {text}"
        if suggestion:
            msg += f" (mungkin maksudnya !{suggestion})"
        super().__init__(msg)


def tokenize(text: str) -> List[str]:
    body = (text or "").strip()
    body = re.sub(r"^[!/.#]", "", body)
    try:
        tokens = shlex.split(body)
    except ValueError:
        tokens = body.split()
    return [t.strip() for t in tokens if t.strip()]


_OPTIONAL_PARAM = re.compile(r"^<(\w+)\?>$")


def _token_matches(pattern_tok: str, token: str) -> Optional[str]:
    """None = tidak cocok, '' = token literal/flag cocok, selain itu = nilai param."""
    if pattern_tok.startswith("<"):
        return token
    if pattern_tok.startswith("?"):
        # flag opsional: cocok bila user mengetik namanya (!pos chat)
        return "" if pattern_tok[1:].lower() == token.lower() else None
    return "" if pattern_tok.lower() == token.lower() else None


def _match(spec: CommandSpec, tokens: Sequence[str]) -> Optional[Dict[str, object]]:
    pat = spec.tokens
    args: Dict[str, object] = {}
    i = 0
    for ptok in pat:
        opt_param = _OPTIONAL_PARAM.match(ptok)
        if opt_param:  # <category?> — nilai opsional bebas
            if i < len(tokens):
                args[opt_param.group(1)] = tokens[i]
                i += 1
            else:
                args[opt_param.group(1)] = False
            continue
        optional = ptok.startswith("?")
        key = ptok.strip("<>?")
        if i >= len(tokens):
            if optional:
                args[key] = False
                continue
            return None
        got = _token_matches(ptok, tokens[i])
        if got is None:
            if optional:
                args[key] = False
                continue
            return None
        if ptok.startswith("<"):
            args[key] = got
        elif optional:
            args[key] = True
        i += 1
    if i != len(tokens):
        return None
    for ptok in pat:
        if ptok.startswith("?"):
            args.setdefault(ptok[1:], False)
        m = _OPTIONAL_PARAM.match(ptok)
        if m:
            args.setdefault(m.group(1), False)
    return args


def parse(text: str, sender: str = "") -> Command:
    # Sintaks cron butuh sisa baris (ekspresi lima field + perintah tujuan).
    # Tangani khusus agar kutip pada "0 2 * * *" tidak hilang saat tokenize.
    body = re.sub(r"^[!/.#]", "", (text or "").strip())
    cron_spec = next((sp for sp in SPECS if sp.name == "cron"), None)
    if cron_spec and re.match(r"^cron\s+", body, re.I):
        m = re.match(r"^cron\s+(add)\s+(['\"])(.*?)\2\s+(.+)$", body, re.I)
        if m:
            return Command(cron_spec, text, {"action": "add", "expr": m.group(3), "text": m.group(4)}, sender)
        m = re.match(r"^cron\s+add\s+(\S+\s+\S+\s+\S+\s+\S+\s+\S+)\s+(.+)$", body, re.I)
        if m:
            return Command(cron_spec, text, {"action": "add", "expr": m.group(1), "text": m.group(2)}, sender)
        m = re.match(r"^cron\s+(list|del|delete|rm)(?:\s+(\S+))?\s*$", body, re.I)
        if m:
            return Command(cron_spec, text, {"action": m.group(1).lower(), "expr": m.group(2) or False}, sender)
    tokens = tokenize(text)
    if not tokens:
        raise ParseError("perintah kosong")
    lowered = [t.lower() for t in tokens]
    for size in range(min(len(tokens), _MAX_PREFIX), -1, -1):
        for spec in _INDEX.get(tuple(lowered[:size]), ()):
            args = _match(spec, tokens)
            if args is not None:
                return Command(spec=spec, raw=text, args=args, sender=sender)
    first = lowered[0]
    hint = ""
    for prefix in _INDEX:
        if prefix and (prefix[0] == first or prefix[0].startswith(first) or first.startswith(prefix[0])):
            hint = " ".join(prefix)
            break
    raise UnknownCommand(text, hint)


# --------------------------------------------------------------------------- #
# Coercion helper untuk handler
# --------------------------------------------------------------------------- #
def arg_nick(args: dict, key: str = "nick") -> str:
    val = str(args.get(key) or "").strip()
    if not val:
        raise ParseError(f"nick wajib diisi ({key})")
    if len(val) > 24:
        raise ParseError("nick terlalu panjang")
    return val


def arg_amount(args: dict, key: str = "amount", suffixes: Optional[dict] = None) -> int:
    return parse_amount(str(args.get(key) or ""), suffixes)


def arg_duration(args: dict, key: str = "duration") -> int:
    return parse_duration(str(args.get(key) or ""))


def arg_coords(args: dict) -> Tuple[int, int]:
    try:
        x, y = int(str(args.get("x"))), int(str(args.get("y")))
    except (TypeError, ValueError) as exc:
        raise ParseError("koordinat harus angka, contoh !relocate 123 456") from exc
    if not (0 <= x <= 1200 and 0 <= y <= 1200):
        raise ParseError("koordinat di luar peta (0-1200)")
    return x, y


def arg_rss_type(args: dict, key: str = "type", units: Optional[dict] = None) -> str:
    raw = str(args.get(key) or "").strip().lower()
    mapping = {k.lower(): k for k in (units or {"F": 1, "S": 1, "W": 1, "O": 1, "G": 1})}
    if raw in RSS_SHORTCUT_TYPES:
        return RSS_SHORTCUT_TYPES[raw]
    if raw in mapping:
        return mapping[raw]
    if raw.upper() in mapping:
        return mapping[raw.upper()]
    raise ParseError(f"tipe rss tidak dikenal: {raw} (pakai F/S/W/O/G atau food/stone/wood/ore/gold)")


def arg_state(args: dict, key: str = "state") -> bool:
    raw = str(args.get(key) or "").strip().lower()
    if raw in {"on", "true", "1", "ya", "yes"}:
        return True
    if raw in {"off", "false", "0", "tidak", "no"}:
        return False
    raise ParseError("nilai harus on atau off")


def arg_flag(args: dict, key: str) -> bool:
    val = args.get(key, False)
    if isinstance(val, str):
        return val.lower() in {"f", "on", "1", "yes", "ya"}
    return bool(val)


def rss_vector(args: dict, suffixes: Optional[dict] = None) -> Dict[str, int]:
    parts = [str(args.get(k) or "0") for k in ("f", "s", "w", "o", "g")]
    return parse_rss_vector(" ".join(parts), suffixes=suffixes)


def iter_specs(category: Optional[str] = None) -> Iterable[CommandSpec]:
    for spec in ALL_SPECS:
        if category is None or spec.category.upper() == category.upper():
            yield spec
