#!/usr/bin/env python3
"""Transcode Jelly source between UTF-8 text and codepage (SBCS) bytes.

usage: sbcs.py encode IN.jelly OUT.sbcs     UTF-8 -> codepage bytes
       sbcs.py decode IN.sbcs OUT.jelly     codepage bytes -> UTF-8
"""
import sys

import jellyenv


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] not in ("encode", "decode"):
        sys.exit(__doc__.strip())
    mode, src, dst = sys.argv[1:]
    if mode == "encode":
        text = open(src, encoding="utf-8").read()
        # Trailing newline in the text file is editor convention, not a link.
        if text.endswith("\n"):
            text = text[:-1]
        open(dst, "wb").write(jellyenv.str_to_sbcs(text))
    else:
        raw = open(src, "rb").read()
        text = jellyenv.sbcs_to_str(raw).replace("\x7f", "\n")
        open(dst, "w", encoding="utf-8").write(text + "\n")


if __name__ == "__main__":
    main()
