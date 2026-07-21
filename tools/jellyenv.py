"""Shared helper: put the vendored Jelly interpreter on sys.path and expose it.

Every Python tool in this repo that needs the reference interpreter imports
through here, so the pin lives in exactly one place (tools/vendor.sh).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "vendor", "jellylanguage")

if not os.path.isdir(VENDOR):
    sys.exit("vendored interpreter missing - run tools/vendor.sh first")

sys.path.insert(0, VENDOR)
sys.setrecursionlimit(1_000_000)

from jelly import code_page                      # noqa: E402
from jelly.interpreter import jelly_eval         # noqa: E402

CHAR_TO_BYTE = {c: i for i, c in enumerate(code_page)}


def sbcs_to_str(raw: bytes) -> str:
    """Jelly-codepage bytes -> the interpreter's internal str form."""
    return "".join(code_page[b] for b in raw)


def str_to_sbcs(text: str) -> bytes:
    """UTF-8-decoded Jelly source -> codepage bytes. Newlines become ¶ (0x7F)."""
    out = bytearray()
    for ch in text:
        if ch == "\n":
            out.append(0x7F)
        else:
            out.append(CHAR_TO_BYTE[ch])
    return bytes(out)


def run_jelly(code: str, left):
    """Evaluate a monadic Jelly program: left argument only, so the main link
    uses monadic chain rules and ⁹ keeps its interpreter default (256).
    This mirrors the compiled convention (_start passes rsi = tagged 256)."""
    return jelly_eval(code, [left])
