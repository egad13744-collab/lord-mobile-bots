"""Engine bot: menerima baris perintah -> otorisasi -> eksekusi -> balasan."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .config import Config
from .custom import CustomSet, load_custom
from .handlers import Cmd, Context, Handlers, Result, build_handlers, help_text
from .i18n import translator_for
from .metrics import Metrics
from .ops import DryRunOps, GameOps, OpsError
from .parser import UnknownCommand, parse
from .roles import PermissionError_
from .schedule import Schedule
from .state import BankStore
from .tasks import TaskQueue
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
        self.t = translator_for(cfg)
        self.custom: CustomSet = load_custom(
            cfg.resolve_path(str(cfg.get("commands.path", "config/commands.yaml")))
        )
        self.metrics = Metrics()
        self.ctx = Context(cfg=cfg, bank=self.bank, ops=ops, logger=self.log.info)
        self.alerts = getattr(ops, "alerts", None)
        self.handlers: Handlers = build_handlers(self.ctx)
        self.limiter = RateLimiter(int(cfg.get("bot.max_commands_per_minute", 20)) or 20)
        self.stats: Dict[str, int] = {"received": 0, "executed": 0, "failed": 0, "ignored": 0}
        self.started_at = time.time()

        # --- lapisan operasional (premium) ---
        self.queue: Optional[TaskQueue] = None
        self.schedule: Optional[Schedule] = None
        if cfg.get("queue.enabled", True):
            self.queue = TaskQueue(
                cfg.resolve_path(cfg.get("queue.path", "state/queue.json")),
                max_pending=int(cfg.get("queue.max_pending", 50) or 50),
            )
            self.ctx.queue = self.queue
        if cfg.get("schedule.enabled", True):
            self.schedule = Schedule(cfg.resolve_path(cfg.get("schedule.path", "state/schedule.json")))
            self.ctx.schedule = self.schedule
        self._commands_since_backup = 0
        self._queue_local = threading.local()

    # ------------------------------------------------------------------ #
    def _log(self, msg: str) -> None:
        self.log.info(msg)

    def handle_line(self, line: str, sender: Optional[str] = None) -> BotReply:
        started = time.perf_counter()
        sender = sender or self.cfg.get("bot.owner_nick", "arken_ega")
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

        # alias & perintah custom dari config/commands.yaml
        text = self.custom.resolve_alias(text)
        head = text.lstrip("!").split(" ", 1)[0].lower()
        custom_cmd = self.custom.lookup(head)
        if custom_cmd:
            try:
                rank = self.bank.roster.authorize(sender, custom_cmd.min_rank)
            except PermissionError_ as exc:
                self.stats["failed"] += 1
                return BotReply(False, f"🔒 {exc}", head, _ms(started), sender)
            if not self.limiter.allow():
                wait = self.limiter.wait_time()
                self.stats["failed"] += 1
                return BotReply(False, f"⏳ terlalu banyak perintah, coba lagi dalam {wait:.0f} detik",
                                f"custom:{head}", _ms(started), sender)
            self.metrics.observe_command(f"custom:{head}", True)
            self.stats["executed"] += 1
            self._log(f"cmd {sender}({rank}) custom:{head}")
            return BotReply(True, custom_cmd.reply, f"custom:{head}", _ms(started), sender)

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

        # Rate limit harus dilakukan sebelum enqueue supaya antrean tidak bisa
        # dipakai untuk melewati batas perintah per menit.
        if not self.limiter.allow():
            wait = self.limiter.wait_time()
            self.stats["failed"] += 1
            return BotReply(
                False, f"⏳ terlalu banyak perintah, coba lagi dalam {wait:.0f} detik",
                parsed.name, _ms(started), sender,
            )

        # Antrian: hanya dipakai bila perangkat SEDANG dipakai alur lain
        # (mode `always` membuat semua perintah pengiriman diantrikan).
        if self.queue is not None and parsed.name in ENQUEUE_DELAYED and self._should_enqueue():
            try:
                job = self.queue.add(text, sender, rank)
            except RuntimeError as exc:
                self.stats["failed"] += 1
                return BotReply(False, f"⚠️ {exc}", parsed.name, _ms(started), sender)
            self.metrics.inc("lmbot_jobs_enqueued_total")
            self.metrics.observe_command(parsed.name, True)
            pos = self.queue.position(job.id)
            return BotReply(
                True, self.t("queue.added", id=job.id, cmd=text, pos=pos),
                parsed.name, _ms(started), sender,
            )

        cmd = Cmd.from_parsed(parsed, rank)
        self._log(f"cmd {sender}({rank}) !{cmd.name} {cmd.args}")
        result: Result = self.handlers.dispatch(cmd)
        self.metrics.observe_command(cmd.name, result.ok)
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
        self._maybe_backup()
        return BotReply(result.ok, msg, cmd.name, _ms(started), sender)

    # ------------------------------------------------------------------ #
    def _should_enqueue(self) -> bool:
        """True bila perintah sebaiknya masuk antrian.

        * `queue.always` -> semua perintah pengiriman diantrikan.
        * default -> hanya bila layar sedang dipakai (DEVICE_LOCK terpegang),
          jadi beban normal tetap dieksekusi langsung (tanpa delay).
        """
        if getattr(self._queue_local, "executing", False):
            return False
        if self.cfg.get("queue.always", False):
            return True
        from .ops import DEVICE_LOCK

        if DEVICE_LOCK.acquire(blocking=False):
            DEVICE_LOCK.release()
            return False
        return True

    # ------------------------------------------------------------------ #
    def start_workers(self) -> None:
        """Nyalakan worker antrian + penjadwal cron (dipanggil `serve`)."""
        from .schedule import Scheduler
        from .tasks import Worker

        if self.queue is not None and not getattr(self, "_worker", None):
            def execute_queued(text, sender):
                self._queue_local.executing = True
                try:
                    return self.handle_and_reply(text, sender or None)
                finally:
                    self._queue_local.executing = False
            self._worker = Worker(
                self.queue,
                executor=execute_queued,
                logger=self.log.info,
            ).start()
        if self.schedule is not None and not getattr(self, "_scheduler", None):
            self._scheduler = Scheduler(
                self.schedule,
                executor=lambda text, sender: self.handle_and_reply(text, sender or None),
                logger=self.log.info,
                interval=float(self.cfg.get("schedule.interval", 20) or 20),
            ).start()

    def stop_workers(self) -> None:
        for attr in ("_worker", "_scheduler"):
            worker = getattr(self, attr, None)
            if worker:
                worker.stop()
                setattr(self, attr, None)

    # ------------------------------------------------------------------ #
    def _maybe_backup(self) -> None:
        """Backup berkala buku besar (default tiap 50 perintah yang ditangani)."""
        if not self.cfg.get("backup.enabled", True):
            return
        every = int(self.cfg.get("backup.every_commands", 50) or 0)
        if every <= 0:
            return
        self._commands_since_backup += 1
        if self._commands_since_backup >= every:
            self._commands_since_backup = 0
            try:
                self.bank.backup(keep=int(self.cfg.get("backup.keep", 7) or 7))
            except OSError as exc:  # pragma: no cover - disk penuh/izin
                self._log(f"backup gagal: {exc}")

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
        q = self.queue.stats() if self.queue else {}
        extra = f" | queue {q.get('queued', 0)}q/{q.get('done', 0)}d" if q else ""
        return (
            f"uptime {self.uptime()} | rx {st['received']} ok {st['executed']} "
            f"fail {st['failed']} skip {st['ignored']} | member {s['members']} "
            f"wl {s['whitelist']} bl {s['blacklist']} tx {s['transactions']}{extra}"
        )

    def metrics_summary(self) -> str:
        """Top perintah + antrian, untuk `:stats` di REPL."""
        rows = self.metrics.top_commands(5)
        parts = [f"{name}: {n}" for name, n in rows] or ["belum ada perintah"]
        q = self.queue.stats() if self.queue else {}
        return "top perintah: " + ", ".join(parts) + (
            f" | antrian {q}" if q else ""
        )


# Perintah yang lebih baik diantrikan daripada dieksekusi saat itu juga:
# pengiriman RSS menyentuh layar, jadi jangan sampai menabrak perintah lain.
ENQUEUE_DELAYED = {"transfer", "donate", "adminrss", "rss"}


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def short_help(cfg, category: Optional[str] = None) -> str:
    return help_text(cfg, category)
