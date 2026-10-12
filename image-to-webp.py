#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Open the Image to WebP desktop app, or run its CLI with arguments."""

import sys

from source.convert import main as cli_main


def main() -> int:
    if len(sys.argv) > 1:
        return cli_main()

    from source.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
