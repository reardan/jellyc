#!/usr/bin/env python3
"""stage0: run a JellyCore program under the reference Jelly interpreter,
with the jellyc I/O convention:

    left argument  = entire input as a list of byte values (ints 0..255)
    program result = flat list of byte values, written raw to the output

This deliberately bypasses jelly.main()/output(), whose codepage text
encoding would corrupt binary output such as ELF files. jelly_eval returns
the raw value, which is all we need.

usage: stage0.py PROGRAM[.sbcs|.jelly] [IN [OUT]]    (IN/OUT default: stdio)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "tools"))
import jellyenv


def flatten_bytes(value, out: bytearray) -> None:
    if isinstance(value, list):
        for item in value:
            flatten_bytes(item, out)
        return
    if isinstance(value, bool) or not isinstance(value, int):
        sys.exit(f"stage0: program result contains a non-integer: {value!r}")
    if not 0 <= value <= 255:
        sys.exit(f"stage0: program result byte out of range: {value}")
    out.append(value)


def main() -> None:
    if not 2 <= len(sys.argv) <= 4:
        sys.exit(__doc__.strip())
    prog_path = sys.argv[1]
    in_path = sys.argv[2] if len(sys.argv) > 2 else None
    out_path = sys.argv[3] if len(sys.argv) > 3 else None

    raw = open(prog_path, "rb").read()
    if prog_path.endswith(".jelly"):
        text = raw.decode("utf-8")
        if text.endswith("\n"):
            text = text[:-1]
        # Interpreter splits links on '¶' (U+00B6, code page byte 0x7f).
        code = text.replace("\n", "¶")
    else:
        code = jellyenv.sbcs_to_str(raw)

    data = open(in_path, "rb").read() if in_path else sys.stdin.buffer.read()
    result = jellyenv.run_jelly(code, list(data))

    out = bytearray()
    flatten_bytes(result, out)
    if out_path:
        open(out_path, "wb").write(bytes(out))
    else:
        sys.stdout.buffer.write(bytes(out))


if __name__ == "__main__":
    main()
