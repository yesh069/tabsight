"""Command line entry point: ``tabsight``. Commands arrive in Phase 9."""

from __future__ import annotations

import argparse

from tabsight._version import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tabsight", description=__doc__)
    parser.add_argument("--version", action="version", version=f"tabsight {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
