"""Dependency-free error message helpers shared by application front ends."""

from __future__ import annotations


def format_action_error(action: str, exc: OSError | ValueError) -> str:
    """Format an actionable error without losing the original failure detail."""

    return f"行动失败：{action}：{exc}"
