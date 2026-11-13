"""Engine bot: menerima baris perintah -> otorisasi -> eksekusi -> balasan."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .config import Config
from .handlers import Cmd, Context, Handlers, Result, build_handlers, help_text
from .ops import DryRunOps, GameOps, OpsError
from .parser import UnknownCommand, parse
from .roles import PermissionError_
from .state import BankStore
from .utils import ParseError, RateLimiter

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"


def setup_logging(cfg: Config, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("lmbot")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter(LOG_FORMAT)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    try:
        log_path = cfg.resolve_path(cfg.get("bot.log_file", "logs/bot.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass
    logger.propagate = False
    return logger


@dataclass
class BotReply:
    ok: bool
    message: str
    command: str = ""
    duration_ms: int = 0
    sender: str = ""


class Bot:
    def __init__(
        self,
        cfg: Config,
        ops: GameOps,
        bank: Optional[BankStore] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.cfg = cfg
        if cfg.get("bot.dry_run", False):
            ops = DryRunOps(ops, logger=(logger or setup_logging(cfg)).info)
        self.ops = ops
        self.bank = bank or BankStore(cfg)
        self.log = logger or setup_logging(cfg)
        self.ctx = Context(cfg=cfg, bank=self.bank, ops=ops, logger=self.log.info)
        self.alerts = getattr(ops, "alerts", None)
        self.handlers: Handlers = build_handlers(self.ctx)
        self.limiter = RateLimiter(int(cfg.get("bot.max_commands_per_minute", 20)) or 20)
        self.stats: Dict[str, int] = {"received": 0, "executed": 0, "failed": 0, "ignored": 0}
        self.started_at = time.time()

    # ------------------------------------------------------------------ #
    def _log(self, msg: str) -> None:
        self.log.info(msg)

    def handle_line(self, line: str, sender: Optional[str] = None) -> BotReply:
        started = time.perf_counter()
        sender = sender or self.cfg.get("bot.owner_nick", "lady_ayu")
        text = (line or "").strip()
        self.stats["received"] += 1
        if not text:
            self.stats["ignored"] += 1
            return BotReply(False, "", "", 0, sender)

        prefix = self.cfg.get("ui.msg_prefix", "R4") or ""
        if text.startswith("!") or text.startswith("/"):
            pass
        elif prefix and text.upper().startswith(f"[{prefix.upper()}]"):
            text = text[len(prefix) + 2 :].strip()
        else:
            self.stats["ignored"] += 1
            return BotReply(False, "", "", 0, sender)

        try:
            parsed = parse(text, sender)
        except UnknownCommand as exc:
            self.stats["failed"] += 1
            hint = help_text(self.cfg) if self.cfg.get("bot.unknown_command_hint", True) else ""
            msg = str(exc)
            if hint:
                msg += "\n\n" + short_help(self.cfg)
            return BotReply(False, msg, "?", _ms(started), sender)
        except ParseError as exc:
            self.stats["failed"] += 1
            return BotReply(False, f"⚠️ {exc}", "?", _ms(started), sender)

        # otorisasi
        if self.bank.roster.is_blacklisted(sender):
            self.stats["failed"] += 1
            self._log(f"tolak {sender}: blacklist")
            return BotReply(False, "🚫 kamu ada di blacklist", parsed.name, _ms(started), sender)
        try:
            rank = self.bank.roster.authorize(sender, parsed.spec.min_rank)
        except PermissionError_ as exc:
            self.stats["failed"] += 1
            self._log(f"tolak {sender}: {exc}")
            return BotReply(
                False,
                f"🔒 {exc}\nPerintah !{parsed.spec.pattern} butuh {parsed.spec.min_rank}+",
                parsed.name, _ms(started), sender,
            )

        # rate limit
        if not self.limiter.allow():
            wait = self.limiter.wait_time()
            self.stats["failed"] += 1
            return BotReply(
                False, f"⏳ terlalu banyak perintah, coba lagi dalam {wait:.0f} detik",
                parsed.name, _ms(started), sender,
            )

        cmd = Cmd.from_parsed(parsed, rank)
        self._log(f"cmd {sender}({rank}) !{cmd.name} {cmd.args}")
        result: Result = self.handlers.dispatch(cmd)
        if result.ok:
            self.stats["executed"] += 1
        else:
            self.stats["failed"] += 1
            if self.alerts and result.error:
                self.alerts.send(
                    "error", f"perintah !{parsed.spec.tokens[0]} gagal", result.error,
                    sender=sender, command=cmd.name,
                )
        msg = result.reply if result.ok else f"⚠️ {result.error}"
        return BotReply(result.ok, msg, cmd.name, _ms(started), sender)

    # ------------------------------------------------------------------ #
    def handle_and_reply(self, line: str, sender: Optional[str] = None) -> BotReply:
        reply = self.handle_line(line, sender)
        reply_text = self.cfg.get("bot.reply_prefix", "") + reply.message
        if reply.message and self.cfg.get("bot.reply_confirm", True):
            try:
                self.ops.send_chat(reply_text)
            except OpsError as exc:
                self._log(f"gagal kirim balasan: {exc}")
        return reply

    # ------------------------------------------------------------------ #
    def uptime(self) -> str:
        secs = int(time.time() - self.started_at)
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def summary(self) -> str:
        st = self.stats
        s = self.bank.stats()
        return (
            f"uptime {self.uptime()} | rx {st['received']} ok {st['executed']} "
            f"fail {st['failed']} skip {st['ignored']} | member {s['members']} "
            f"wl {s['whitelist']} bl {s['blacklist']} tx {s['transactions']}"
        )


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def short_help(cfg, category: Optional[str] = None) -> str:
    return help_text(cfg, category)
