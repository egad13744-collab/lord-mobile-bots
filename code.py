#!/usr/bin/env python3
"""Entry point: `python code.py ...` sama dengan `python -m lmbot ...`."""
import sys

from lmbot.cli import main

if __name__ == "__main__":
    sys.exit(main())
