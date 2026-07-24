"""Repository-local CLI wrapper for the knowledge-base builder."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb.builder import create_parser, run_build
from opcua_kb.cli import run_cli


def main() -> None:
    """Parse builder CLI arguments and print generated artifact counts."""

    args = create_parser().parse_args()
    run_cli(lambda: run_build(args))


if __name__ == "__main__":
    main()
