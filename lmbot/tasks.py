"""Antrian pekerjaan persisten + worker tunggal.

Kenapa perlu? Di klan nyata, 5 member bisa minta RSS hampir bersamaan. Tanpa
antrian, permintaan kedua hanya "menunggu lock" tanpa status, dan hilang total
bila bot restart. Dengan antrian:

* setiap permintaan punya **id** dan status yang bisa dicek (`!queue`, `!jobs`);
* prioritas ditentukan rank pengirim (owner > R5 > R4 > member);
* job disimpan ke `state/queue.json` sehingga **selamat dari restart**;
* satu worker menjalankan job berurutan — tidak ada tap yang bertabrakan;
* kegagalan dicatat dan bisa di-retry (`!retry <id>`).

Antrian tidak butuh SQLite: file JSON kecil + lock cukup untuk beban 1 bot.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

PRIORITY_BY_RANK = {"R6": 0, "R5": 1, "R4": 2, "R3": 3, "R2": 4, "R1": 5}
DONE_STATES = ("done", "failed", "cancelled")


@dataclass
class Job:
    id: int
    text: str
    sender: str
    priority: int = 5
    status: str = "queued"
    created: float = field(default_factory=time.time)
    started: float = 0.0
    finished: float = 0.0
    attempts: int = 0
    error: str = ""
    result: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "text": self.text, "sender": self.sender,
            "priority": self.priority, "status": self.status,
            "created": self.created, "started": self.started,
            "finished": self.finished, "attempts": self.attempts,
            "error": self.error, "result": self.result,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Job":
        return cls(
            id=int(d.get("id", 0)), text=str(d.get("text", "")),
            sender=str(d.get("sender", "")), priority=int(d.get("priority", 5)),
            status=str(d.get("status", "queued")), created=float(d.get("created", 0) or 0),
            started=float(d.get("started", 0) or 0), finished=float(d.get("finished", 0) or 0),
            attempts=int(d.get("attempts", 0) or 0), error=str(d.get("error", "")),
            result=str(d.get("result", "")),
        )

    def describe(self) -> str:
        return f"#{self.id} [{self.status}] {self.text} — {self.sender}"


class TaskQueue:
    """Antrian job persisten. Aman dipakai dari beberapa thread."""

    def __init__(self, path: str | Path, max_pending: int = 50):
        self.path = Path(path)
        self.max_pending = max(1, int(max_pending))
        self._lock = threading.RLock()
        self.jobs: List[Job] = []
        self._next_id = 1
        self.load()

    # -- persist -- #
    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self.jobs = [Job.from_dict(d) for d in data.get("jobs", [])]
        # Proses mati ketika job berjalan: antrekan ulang, jangan hilangkan job.
        recovered = False
        for job in self.jobs:
            if job.status == "running":
                job.status = "queued"
                job.error = "dipulihkan setelah bot restart"
                recovered = True
        self._next_id = int(data.get("next_id", 1) or 1)
        if recovered:
            self.save()

    def save(self) -> None:
        with self._lock:
            payload = {"next_id": self._next_id, "jobs": [j.to_dict() for j in self.jobs[-500:]]}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)

    # -- mutasi -- #
    def add(self, text: str, sender: str, rank: str = "R1") -> Job:
        with self._lock:
            pending = [j for j in self.jobs if j.status not in DONE_STATES]
            if len(pending) >= self.max_pending:
                raise RuntimeError(f"antrian penuh ({self.max_pending} job menunggu)")
            job = Job(id=self._next_id, text=text.strip(), sender=sender,
                      priority=PRIORITY_BY_RANK.get((rank or "R1").upper(), 5))
            self._next_id += 1
            self.jobs.append(job)
            self.save()
            return job

    def next_job(self) -> Optional[Job]:
        with self._lock:
            queued = [j for j in self.jobs if j.status == "queued"]
            if not queued:
                return None
            queued.sort(key=lambda j: (j.priority, j.created))
            job = queued[0]
            job.status = "running"
            job.started = time.time()
            job.attempts += 1
            self.save()
            return job

    def finish(self, job_id: int, ok: bool, result: str = "", error: str = "") -> None:
        with self._lock:
            for job in self.jobs:
                if job.id == job_id:
                    job.status = "done" if ok else "failed"
                    job.finished = time.time()
                    job.result = result[:400]
                    job.error = error[:400]
                    break
            self.save()

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            for job in self.jobs:
                # Job aktif sedang/akan menyentuh game; tidak bisa dibatalkan aman.
                if job.id == job_id and job.status == "queued":
                    job.status = "cancelled"
                    job.finished = time.time()
                    self.save()
                    return True
            return False

    def retry(self, job_id: int) -> bool:
        with self._lock:
            for job in self.jobs:
                if job.id == job_id and job.status == "failed":
                    job.status = "queued"
                    job.error = ""
                    self.save()
                    return True
            return False

    def position(self, job_id: int) -> int:
        with self._lock:
            queued = [j.id for j in sorted(
                (j for j in self.jobs if j.status == "queued"),
                key=lambda j: (j.priority, j.created),
            )]
        return queued.index(job_id) + 1 if job_id in queued else 0

    # -- baca -- #
    def pending_count(self) -> int:
        return len([j for j in self.jobs if j.status in ("queued", "running")])

    def list(self, status: Optional[str] = None, limit: int = 10) -> List[Job]:
        with self._lock:
            rows = [j for j in self.jobs if status is None or j.status == status]
            if status == "queued":
                rows.sort(key=lambda j: (j.priority, j.created))
        return rows[-limit:] if status != "queued" else rows[:limit]

    def stats(self) -> Dict[str, int]:
        out = {s: 0 for s in ("queued", "running", "done", "failed", "cancelled")}
        with self._lock:
            for job in self.jobs:
                out[job.status] = out.get(job.status, 0) + 1
        return out


class Worker:
    """Menjalankan job dari TaskQueue satu per satu di thread latar."""

    def __init__(self, queue: TaskQueue, executor: Callable[[str, str], object],
                 logger=None, poll: float = 0.5):
        self.queue = queue
        self.executor = executor
        self.log = logger
        self.poll = poll
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.processed = 0

    def start(self) -> "Worker":
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(target=self._loop, name="lmbot-worker", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            job = self.queue.next_job()
            if not job:
                self._stop.wait(self.poll)
                continue
            try:
                reply = self.executor(job.text, job.sender)
                ok = bool(getattr(reply, "ok", True))
                msg = str(getattr(reply, "message", "") or "")
                self.queue.finish(job.id, ok, result=msg, error="" if ok else msg)
                if self.log:
                    self.log(f"[queue] job #{job.id} {'ok' if ok else 'gagal'}: {job.text}")
            except Exception as exc:  # pragma: no cover - jaring pengaman worker
                self.queue.finish(job.id, False, error=str(exc))
                if self.log:
                    self.log(f"[queue] job #{job.id} error: {exc!r}")
            self.processed += 1
