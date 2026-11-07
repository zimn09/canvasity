"""Canvasity entry point."""

from __future__ import annotations

import sys

from canvasity.app import run

if __name__ == "__main__":
    raise SystemExit(run(sys.argv))
