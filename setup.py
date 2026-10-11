#!/usr/bin/env python3
"""Install this tool's requirements, optionally in a local virtual environment."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"
VENV = ROOT / ".venv"


def run(command: list[str], *, print_only: bool) -> None:
    print("[CMD]", subprocess.list2cmdline(command))
    if print_only:
        return
    subprocess.run(command, cwd=ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", action="store_true", help="Create or reuse .venv beside setup.py")
    parser.add_argument("--print-only", action="store_true", help="Show commands without running them")
    args = parser.parse_args(argv)

    if not REQUIREMENTS.is_file():
        parser.error(f"requirements file not found: {REQUIREMENTS}")

    python = Path(sys.executable)
    if args.venv:
        if not VENV.is_dir():
            run([str(python), "-m", "venv", str(VENV)], print_only=args.print_only)
        python = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if not args.print_only and not python.is_file():
            parser.error(f"virtual environment Python not found: {python}")

    try:
        run([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)], print_only=args.print_only)
    except subprocess.CalledProcessError as error:
        return error.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
