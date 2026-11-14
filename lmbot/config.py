"""Pemuatan & validasi konfigurasi (config/settings.yaml)."""
from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"

DEFAULTS: Dict[str, Any] = {
    "device": {
        "driver": "adb",
        "adb_path": "adb",
        "serial": "127.0.0.1:16384",
        "width": 1280,
        "height": 720,
        "density": 240,
        "auto_connect": True,
        "mumu_manager": "",
        "screenshot_timeout": 20,
        "profiles": {},
    },
    "ui": {
        "chat_button": [0.06, 0.92],
        "chat_input": [0.50, 0.86],
        "chat_send": [0.94, 0.86],
        "chat_close": [0.94, 0.14],
        "chat_open_wait": 1.2,
        "chat_reply_wait": 2.0,
        "chat_tail": "",
        "msg_prefix": "R4",
        "lang": "id",
    },
    "bot": {
        "name": "LMBot",
        "profile": "default",
        "owner_nick": "arken_ega",
        "allowed_senders": ["arken_ega"],
        "guild_name": "GUILD",
        "poll_interval": 3.0,
        "max_commands_per_minute": 20,
        "dry_run": False,
        "confirm_risky": True,
        "reply_confirm": True,
        "log_file": "logs/bot.log",
        "unknown_command_hint": True,
    },
    "safety": {
        "max_rss_per_transfer": 300_000_000,
        "max_balance_per_command": 100_000_000,
        "daily_limit_per_type": 0,      # 0 = tanpa batas kuota harian
        "daily_limit_all_types": 0,
        "cooldown_between_transfers": 2.0,
        "stop_if_not_in_guild_map": True,
        "whitelist_enforced": True,
    },
    "bank": {
        "path": "state/bank.json",
        "save_every_command": True,
        "rss_units": {
            "F": {"key": "food", "label": "Food"},
            "S": {"key": "stone", "label": "Stone"},
            "W": {"key": "wood", "label": "Wood"},
            "O": {"key": "ore", "label": "Ore"},
            "G": {"key": "gold", "label": "Gold"},
        },
        "amount_suffixes": {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000},
    },
    "flows": {
        "dir": "config/flows",
        "default_flow": "guild_bank",
        "step_timeout": 15.0,
        "tap_jitter": 4,
        "max_retries": 1,
    },
    "templates": {"dir": "assets/templates", "threshold": 0.86},
    "vision": {"min_confidence": 0.5},
    "alerts": {
        "file": "logs/alerts.jsonl",
        "webhook_url": "",
        "min_level": "warn",
        "throttle_seconds": 30,
    },
    "queue": {
        "enabled": True,
        "path": "state/queue.json",
        "max_pending": 50,
        "always": False,        # true = semua pengiriman lewat antrian
    },
    "schedule": {"enabled": True, "path": "state/schedule.json", "interval": 20.0},
    "backup": {"enabled": True, "keep": 7, "every_commands": 50},
    "watchdog": {"enabled": True, "interval": 30.0, "fail_threshold": 3},
    "ocr": {"dir": "assets/ocr", "min_score": 0.72},
    "commands": {"path": "config/commands.yaml"},
    "diagnostics": {"enabled": True},
    "web": {
        "enabled": False, "host": "0.0.0.0", "port": 8081, "token": "",
        "roles": {}, "identities": {}, "rate_limit_per_minute": 60,
        "access_log": "logs/access.jsonl",
    },
}


class ConfigError(Exception):
    pass


@dataclass
class Config:
    data: Dict[str, Any] = field(default_factory=dict)
    path: Path = DEFAULT_PATH

    # ---- akses ---- #
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def section(self, name: str) -> Dict[str, Any]:
        val = self.data.get(name, {})
        return val if isinstance(val, dict) else {}

    # ---- turunan ---- #
    @property
    def root(self) -> Path:
        """Folder kerja bot (tempat logs/, state/, assets/ relatif)."""
        base = self.path.resolve().parent.parent
        return Path(self.get("bot.workdir") or base).resolve()

    def resolve_path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (self.root / p)

    def save(self, backup: bool = True) -> Path:
        """Atomically persist settings; optionally preserve the original as .bak."""
        import shutil
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if backup and self.path.exists():
            shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(yaml.safe_dump(self.data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        os.replace(tmp, self.path)
        return self.path


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | os.PathLike | None = None, profile: str | None = None) -> Config:
    p = Path(path) if path else DEFAULT_PATH
    raw: Dict[str, Any] = {}
    if p.exists():
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - pesan ramah
            raise ConfigError(f"YAML tidak valid di {p}: {exc}") from exc
    elif path:
        raise ConfigError(f"File konfigurasi tidak ditemukan: {p}")

    env_serial = os.environ.get("LMBOT_SERIAL")
    data = _deep_merge(DEFAULTS, raw)

    # Profil per-instance: `device.profiles.<nama>` menimpa `device.*`
    profile = profile or os.environ.get("LMBOT_PROFILE") or data.get("bot", {}).get("profile") or ""
    profiles = data.get("device", {}).get("profiles") or {}
    if profile and not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", str(profile)):
        raise ConfigError("nama instance hanya boleh berisi huruf, angka, _ dan -")
    if profile:
        profile_device = profiles.get(profile) or {}
        data["device"] = _deep_merge(
            {k: v for k, v in data["device"].items() if k != "profiles"},
            profile_device,
        )
        data["bot"]["profile"] = profile
        data["device"]["profiles"] = profiles
        # Pisahkan state per emulator agar saldo/transaksi tidak tercampur.
        if profile != "default":
            data["bank"]["path"] = f"state/{profile}/bank.json"
            for section, key, fallback in (("queue", "path", f"state/{profile}/queue.json"),
                                           ("schedule", "path", f"state/{profile}/schedule.json")):
                data[section][key] = fallback
    if env_serial:
        data["device"]["serial"] = env_serial

    cfg = Config(data=data, path=p)
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    dev = cfg.section("device")
    if dev.get("driver") not in {"adb", "mock", "script"}:
        raise ConfigError("device.driver harus 'adb', 'mock', atau 'script'")
    for key in ("width", "height"):
        val = dev.get(key)
        if not isinstance(val, int) or val <= 0:
            raise ConfigError(f"device.{key} harus bilangan bulat positif")

    bot = cfg.section("bot")
    if not bot.get("allowed_senders"):
        raise ConfigError("bot.allowed_senders minimal berisi satu nick")

    profiles = cfg.get("device.profiles") or {}
    if not isinstance(profiles, dict):
        raise ConfigError("device.profiles harus berupa mapping nama -> pengaturan")
    for name, settings in profiles.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", str(name)):
            raise ConfigError(f"nama profil device tidak valid: {name!r}")
        if not isinstance(settings, dict):
            raise ConfigError(f"device.profiles.{name} harus berupa mapping")

    for limit_name in ("safety.daily_limit_per_type", "safety.daily_limit_all_types"):
        try:
            if int(cfg.get(limit_name, 0) or 0) < 0:
                raise ConfigError(f"{limit_name} tidak boleh negatif")
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{limit_name} harus bilangan bulat") from exc

    units = cfg.get("bank.rss_units", {})
    for code in ("F", "S", "W", "O", "G"):
        if code not in units:
            raise ConfigError(f"bank.rss_units kehilangan kode '{code}'")
