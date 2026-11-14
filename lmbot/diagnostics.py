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

    web_roles = cfg.get("web.roles") or {}
    legacy_token = str(cfg.get("web.token") or "").strip()
    role_tokens = [str(v) for v in web_roles.values() if str(v).strip()] if isinstance(web_roles, dict) else []
    if cfg.get("web.enabled") and not legacy_token and not role_tokens:
        found.append(
            "web.enabled tanpa token: endpoint hanya menerima loopback; set web.roles untuk akses LAN."
        )
    for value in ([legacy_token] if legacy_token else []) + role_tokens:
        if len(value) < 24:
            found.append("token web lebih pendek dari 24 karakter; ganti dengan rahasia acak yang panjang.")
            break

    limit = int(cfg.get("safety.max_rss_per_transfer", 0) or 0)
    if limit <= 0 or limit > 5_000_000_000:
        found.append(f"safety.max_rss_per_transfer = {limit:,} tidak wajar (cek konfigurasi).")

    for msg in found:
        try:
            emit(f"⚠️  {msg}")
        except Exception:
            pass
    return found
