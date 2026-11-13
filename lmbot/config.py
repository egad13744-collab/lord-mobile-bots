"""Pemuatan & validasi konfigurasi (config/settings.yaml)."""
from __future__ import annotations

import copy
import os
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
        "owner_nick": "lady_ayu",
        "allowed_senders": ["lady_ayu"],
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
    "diagnostics": {"enabled": True},
    "web": {"enabled": False, "host": "0.0.0.0", "port": 8081, "token": ""},
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


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | os.PathLike | None = None) -> Config:
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

    units = cfg.get("bank.rss_units", {})
    for code in ("F", "S", "W", "O", "G"):
        if code not in units:
            raise ConfigError(f"bank.rss_units kehilangan kode '{code}'")
