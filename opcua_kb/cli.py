"""Shared error handling for command-line entry points."""

from __future__ import annotations

import sys
from collections.abc import Callable


def run_cli(action: Callable[[], None]) -> None:
    """Run a parsed CLI action and render expected operational errors."""

    try:
        action()
    except (OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
