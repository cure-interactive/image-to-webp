#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Open the Image to WebP desktop app, or run its CLI with arguments."""

from pathlib import Path
import shutil
import subprocess
import sys


def _gui_import_error() -> ImportError | None:
    """Check GUI dependencies before importing the app's GUI module."""
    try:
        import tkinter  # noqa: F401
        import PIL  # noqa: F401
        import customtkinter  # noqa: F401
        import CTkToolTip  # noqa: F401
    except ImportError as error:
        return error
    return None


def _run_gui() -> int:
    error = _gui_import_error()
    if error is not None:
        candidate = shutil.which("python") if sys.platform == "win32" else None
        if candidate and Path(candidate).resolve() != Path(sys.executable).resolve():
            try:
                probe = subprocess.run(
                    [candidate, "-c", "import tkinter, PIL, customtkinter, CTkToolTip"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
                if probe.returncode == 0:
                    return subprocess.call([candidate, str(Path(__file__).resolve())])
            except OSError:
                pass
        print(f"Cannot open Image to WebP: {error}", file=sys.stderr)
        print("Use a Python with Tkinter and the packages in requirements.txt, "
              "then run python image-to-webp.py.", file=sys.stderr)
        return 1

    from source.gui import main as gui_main
    return gui_main()


def main() -> int:
    if len(sys.argv) > 1:
        from source.convert import main as cli_main
        return cli_main()

    return _run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
