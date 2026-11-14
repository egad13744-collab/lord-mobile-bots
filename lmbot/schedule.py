"""Penjadwalan sederhana dengan sintaks cron 5 field.

Format: `menit jam tanggal bulan hari-dalam-minggu`

    *      semua nilai
    2       tepat jam 2
    */15   setiap 15
    1-5    rentang
    1,3,5  daftar

Contoh:
    0 2 * * *   -> tiap hari 02:00
    */30 * * * * -> tiap 30 menit
    0 8 * * 1  -> tiap Senin 08:00

Job disimpan di `state/schedule.json` sehingga tahan restart, dan dijalankan
oleh thread `Scheduler` yang memeriksa setiap 20 detik.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))


class CronError(ValueError):
    pass


def _parse_field(expr: str, lo: int, hi: int) -> set:
    out: set = set()
    for part in str(expr).split(","):
        part = part.strip()
        if not part:
            raise CronError("field kosong")
        step = 1
        if "/" in part:
            part, _, step_s = part.partition("/")
            if not step_s.isdigit() or int(step_s) <= 0:
                raise CronError(f"step tidak valid: {step_s}")
            step = int(step_s)
        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part:
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                raise CronError(f"rentang tidak valid: {part}")
            start, end = int(a), int(b)
        elif part.isdigit():
            start = end = int(part)
        else:
            raise CronError(f"nilai tidak valid: {part}")
        if start < lo or end > hi or start > end:
            raise CronError(f"di luar batas {lo}-{hi}: {part}")
        out.update(range(start, end + 1, step))
    return out


def parse_cron(expr: str) -> List[set]:
    fields = str(expr).split()
    if len(fields) != 5:
        raise CronError("cron harus 5 field: menit jam tanggal bulan hari")
    return [_parse_field(f, lo, hi) for f, (lo, hi) in zip(fields, FIELD_RANGES)]


def matches(expr: str, when: Optional[time.struct_time] = None) -> bool:
    """True bila waktu `when` cocok dengan ekspresi cron."""
    t = when or time.localtime()
    minute, hour, day, month, weekday = parse_cron(expr)
    # Python: Senin=0, cron: Minggu=0
    cron_dow = (t.tm_wday + 1) % 7
    return (
        t.tm_min in minute and t.tm_hour in hour and t.tm_mday in day
        and t.tm_mon in month and cron_dow in weekday
    )


def describe(expr: str) -> str:
    """Deskripsi manusiawi singkat untuk `!cron list`."""
    try:
        minute, hour, day, month, dow = [sorted(x) for x in parse_cron(expr)]
    except CronError:
        return "ekspresi tidak valid"
    if (len(minute), len(hour), len(day), len(month), len(dow)) == (60, 24, 31, 12, 7):
        return "setiap menit"
    if len(minute) == 1 and len(hour) == 1 and len(day) == 31 and len(month) == 12:
        if len(dow) == 7:
            return f"harian {hour[0]:02d}:{minute[0]:02d}"
        hari = ", ".join(["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"][d] for d in dow)
        return f"{hari} {hour[0]:02d}:{minute[0]:02d}"
    if len(hour) == 24 and len(day) == 31 and len(month) == 12 and len(dow) == 7:
        if len(minute) == 1:
            return f"tiap jam menit ke-{minute[0]}"
        return f"setiap {60 // max(1, len(minute))} menit"
    return f"cron {expr}"


@dataclass
class CronJob:
    id: int
    expr: str
    text: str
    sender: str
    enabled: bool = True
    last_run: float = 0.0
    last_minute: str = ""      # "YYYY-MM-DD HH:MM" agar tidak jalan 2x di menit sama
    runs: int = 0
    last_error: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "expr": self.expr, "text": self.text, "sender": self.sender,
            "enabled": self.enabled, "last_run": self.last_run,
            "last_minute": self.last_minute, "runs": self.runs, "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "CronJob":
        return cls(
            id=int(d.get("id", 0)), expr=str(d.get("expr", "")), text=str(d.get("text", "")),
            sender=str(d.get("sender", "")), enabled=bool(d.get("enabled", True)),
            last_run=float(d.get("last_run", 0) or 0), last_minute=str(d.get("last_minute", "")),
            runs=int(d.get("runs", 0) or 0), last_error=str(d.get("last_error", "")),
        )


class Schedule:
    """Daftar job cron yang persisten di disk."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.jobs: List[CronJob] = []
        self._next_id = 1
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self.jobs = [CronJob.from_dict(d) for d in data.get("jobs", [])]
        self._next_id = int(data.get("next_id", 1) or 1)

    def save(self) -> None:
        with self._lock:
            payload = {"next_id": self._next_id, "jobs": [j.to_dict() for j in self.jobs]}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)

    def add(self, expr: str, text: str, sender: str) -> CronJob:
        parse_cron(expr)  # validasi dulu: error sebelum disimpan
        # Jangan jadwalkan aksi berisiko (relokasi, transfer, stop, dll).
        from .parser import parse
        try:
            command = parse(text, sender)
        except Exception as exc:
            raise CronError(f"perintah jadwal tidak valid: {exc}") from exc
        safe_names = {"bal", "top", "quota", "audit", "queue", "jobs", "version", "help"}
        if command.spec.risky or command.name not in safe_names:
            raise CronError("jadwal hanya menerima perintah baca/status yang diizinkan")
        if command.name == "audit" and str(command.args.get("action", "verify")) not in {"verify", "log"}:
            raise CronError("aksi audit tidak aman untuk dijadwalkan")
        with self._lock:
            job = CronJob(id=self._next_id, expr=expr.strip(), text=text.strip(), sender=sender)
            self._next_id += 1
            self.jobs.append(job)
            self.save()
            return job

    def remove(self, job_id: int) -> bool:
        with self._lock:
            before = len(self.jobs)
            self.jobs = [j for j in self.jobs if j.id != job_id]
            if len(self.jobs) != before:
                self.save()
                return True
            return False

    def due(self, when: Optional[time.struct_time] = None) -> List[CronJob]:
        t = when or time.localtime()
        stamp = time.strftime("%Y-%m-%d %H:%M", t)
        out = []
        with self._lock:
            for job in self.jobs:
                if not job.enabled or job.last_minute == stamp:
                    continue
                try:
                    if matches(job.expr, t):
                        job.last_minute = stamp
                        job.last_run = time.time()
                        job.runs += 1
                        out.append(job)
                except CronError as exc:
                    job.last_error = str(exc)
            if out:
                self.save()
        return out


class Scheduler:
    """Thread yang memeriksa job jatuh tempo dan menyerahkannya ke executor."""

    def __init__(self, schedule: Schedule, executor: Callable[[str, str], object],
                 logger=None, interval: float = 20.0):
        self.schedule = schedule
        self.executor = executor
        self.log = logger
        self.interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "Scheduler":
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(target=self._loop, name="lmbot-scheduler", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def tick(self) -> List[CronJob]:
        ran = []
        for job in self.schedule.due():
            try:
                reply = self.executor(job.text, job.sender or "cron")
                if getattr(reply, "ok", True):
                    job.last_error = ""
                    ran.append(job)
                    if self.log:
                        self.log(f"[cron] #{job.id} {job.text}")
                else:
                    job.last_error = str(getattr(reply, "message", "perintah gagal"))[:300]
                    self.schedule.save()
                    if self.log:
                        self.log(f"[cron] #{job.id} gagal: {job.last_error}")
            except Exception as exc:  # pragma: no cover
                job.last_error = str(exc)
                self.schedule.save()
                if self.log:
                    self.log(f"[cron] #{job.id} gagal: {exc!r}")
        return ran

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.interval)
