"""Peringatan dini saat konfigurasi masih default & berisiko."""
from __future__ import annotations

from typing import Callable, List

WARNINGS = []


def warn_insecure_defaults(cfg, emit: Callable[[str], None]) -> List[str]:
    """Kembalikan daftar peringatan; juga dikirim ke `emit` (biasanya log.warning)."""
    found: List[str] = []

    allowed = list(cfg.get("bot.allowed_senders") or [])
    if any(str(n).lower() == "arken_ega" for n in allowed):
        found.append(
            "bot.allowed_senders masih berisi nick contoh 'arken_ega'. Ganti dengan "
            "nick akun bank/leader kamu di config/settings.yaml."
        )

    if not cfg.get("safety.whitelist_enforced", True):
        found.append(
            "safety.whitelist_enforced = false: SEMUA orang di chat bisa memakai bot. "
            "Aktifkan lagi untuk keamanan."
        )

    if cfg.get("bot.confirm_risky", True) is False:
        found.append(
            "bot.confirm_risky = false: !guild/!relocate/!migrate langsung dieksekusi "
            "tanpa konfirmasi 'confirm'."
        )

    webhook = str(cfg.get("alerts.webhook_url") or "").strip()
    if webhook and webhook.startswith("http://"):
        found.append("alerts.webhook_url memakai http:// (tidak terenkripsi). Pakai https://.")

    if cfg.get("web.enabled") and not str(cfg.get("web.token") or "").strip():
        found.append(
            "web.enabled = true tanpa web.token: dashboard bisa dibuka siapa pun di LAN."
        )

    limit = int(cfg.get("safety.max_rss_per_transfer", 0) or 0)
    if limit <= 0 or limit > 5_000_000_000:
        found.append(f"safety.max_rss_per_transfer = {limit:,} tidak wajar (cek konfigurasi).")

    for msg in found:
        try:
            emit(f"⚠️  {msg}")
        except Exception:
            pass
    return found
