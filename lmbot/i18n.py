"""Katalog teks (i18n) — ID/EN.

Semua teks bot yang dilihat user dikumpulkan di sini supaya bisa diganti bahasa
lewat `ui.lang: id|en` tanpa menyentuh logika. Kunci yang tidak ada di katalog
bahasa target otomatis jatuh ke bahasa default (id), jadi tidak pernah kosong.
"""
from __future__ import annotations

from typing import Dict

DEFAULT_LANG = "id"

CATALOG: Dict[str, Dict[str, str]] = {
    "id": {
        "bank.frozen": "⏸️ Bank dijeda {secs} detik",
        "bank.active": "▶️ Bank aktif",
        "err.frozen": "bank sedang dijeda {secs} detik (perintah !stop/!abort)",
        "err.blacklist": "🚫 kamu ada di blacklist",
        "err.not_whitelisted": "{nick} belum terdaftar di whitelist",
        "err.rank": "🔒 {nick} ({rank}) butuh minimal {need}",
        "err.rate": "⏳ terlalu banyak perintah, coba lagi dalam {secs:.0f} detik",
        "err.no_funds": "saldo {label} {nick} hanya {have}, diminta {want}",
        "err.zero": "semua jumlah 0, tidak ada yang dikirim",
        "ok.sent": "✅ Terkirim ke {nick}: {rss}",
        "ok.transfer": "✅ Transfer {label} {amount} ke {nick} berhasil",
        "ok.refund": "gagal mengirim di game, saldo dikembalikan: {err}",
        "queue.added": "🧾 Antrian #{id} dibuat ({cmd}) — posisi {pos}",
        "queue.empty": "🧾 Antrian kosong",
        "quota.left": "sisa kuota {label} hari ini: {left}",
        "quota.exceeded": "kuota {label} hari ini sudah habis ({limit})",
        "audit.ok": "🔐 Rantai audit utuh ({count} entri)",
        "audit.broken": "🚨 Rantai audit tidak utuh atau histori belum punya hash di entri #{idx} — periksa state/transactions.jsonl",
        "undo.none": "tidak ada transaksi yang bisa dibatalkan",
        "undo.done": "↩️ Transaksi #{id} dibatalkan: {detail}",
    },
    "en": {
        "bank.frozen": "⏸️ Bank paused for {secs}s",
        "bank.active": "▶️ Bank active",
        "err.frozen": "bank is paused for {secs}s (!stop/!abort)",
        "err.blacklist": "🚫 you are blacklisted",
        "err.not_whitelisted": "{nick} is not whitelisted",
        "err.rank": "🔒 {nick} ({rank}) needs at least {need}",
        "err.rate": "⏳ too many commands, retry in {secs:.0f}s",
        "err.no_funds": "{label} balance of {nick} is only {have}, requested {want}",
        "err.zero": "all amounts are 0, nothing to send",
        "ok.sent": "✅ Sent to {nick}: {rss}",
        "ok.transfer": "✅ Transferred {label} {amount} to {nick}",
        "ok.refund": "game action failed, balance refunded: {err}",
        "queue.added": "🧾 Job #{id} queued ({cmd}) — position {pos}",
        "queue.empty": "🧾 Queue is empty",
        "quota.left": "{label} quota left today: {left}",
        "quota.exceeded": "daily {label} quota exhausted ({limit})",
        "audit.ok": "🔐 Audit chain intact ({count} entries)",
        "audit.broken": "🚨 Audit chain broken or legacy hash missing at entry #{idx} — check state/transactions.jsonl",
        "undo.none": "nothing to undo",
        "undo.done": "↩️ Transaction #{id} undone: {detail}",
    },
}


class Translator:
    def __init__(self, lang: str = DEFAULT_LANG):
        self.lang = (lang or DEFAULT_LANG).lower()[:2]
        if self.lang not in CATALOG:
            self.lang = DEFAULT_LANG

    def __call__(self, key: str, **kw) -> str:
        table = CATALOG.get(self.lang, {})
        text = table.get(key) or CATALOG[DEFAULT_LANG].get(key) or key
        try:
            return text.format(**kw)
        except (KeyError, IndexError, ValueError):  # pragma: no cover - defensif
            return text

    def has(self, key: str) -> bool:
        return key in CATALOG.get(self.lang, {}) or key in CATALOG[DEFAULT_LANG]


def translator_for(cfg) -> Translator:
    return Translator(str(cfg.get("ui.lang", DEFAULT_LANG) or DEFAULT_LANG))
