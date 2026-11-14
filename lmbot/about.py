"""Identitas & atribusi proyek."""

APP_NAME = "LMBot"
TAGLINE = "Guild Bank Bot — Lord Mobile | MuMu + ADB"
AUTHOR = "Egandika"
AUTHOR_LINE = "Dibuat oleh Egandika"
VERSION = "1.1.0"

# Ditampilkan di banner terminal, `!version`, dan footer dashboard.
CREDIT = f"{AUTHOR_LINE} · {APP_NAME} v{VERSION}"


def credit(short: bool = False) -> str:
    return AUTHOR_LINE if short else CREDIT
