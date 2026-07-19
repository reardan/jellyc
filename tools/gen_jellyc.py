#!/usr/bin/env python3
"""Regenerate jellyc.jelly — table of x86-64 ELF blobs for the Jelly subset.

The compiler users run is jellyc.jelly (pure Jelly). This script only rebuilds
those blobs from the hand-assembled x64 templates.
"""
from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "jellyc.jelly"

BASE = 0x400000
HEADER = 120


def le16(x: int) -> bytes:
    return struct.pack("<H", x & 0xFFFF)


def le32(x: int) -> bytes:
    return struct.pack("<I", x & 0xFFFFFFFF)


def le64(x: int) -> bytes:
    return struct.pack("<Q", x & 0xFFFFFFFFFFFFFFFF)


def build_elf(code: bytes) -> list[int]:
    size = HEADER + len(code)
    entry = BASE + HEADER
    e = bytearray(64)
    e[0:4] = b"\x7fELF"
    e[4], e[5], e[6] = 2, 1, 1
    e[16:18] = le16(2)
    e[18:20] = le16(0x3E)
    e[20:24] = le32(1)
    e[24:32] = le64(entry)
    e[32:40] = le64(64)
    e[52:54] = le16(64)
    e[54:56] = le16(56)
    e[56:58] = le16(1)
    p = bytearray(56)
    p[0:4] = le32(1)
    p[4:8] = le32(7)
    p[16:24] = le64(BASE)
    p[24:32] = le64(BASE)
    p[32:40] = le64(size)
    p[40:48] = le64(size)
    p[48:56] = le64(0x1000)
    return list(e + p + code)


class Asm:
    def __init__(self, org: int) -> None:
        self.org = org
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, int]] = []

    def L(self, name: str) -> None:
        self.labels[name] = len(self.buf)

    def emit(self, *bs: int) -> None:
        for b in bs:
            self.buf.append(b & 0xFF)

    def rel32(self, label: str) -> None:
        pos = len(self.buf)
        self.emit(0, 0, 0, 0)
        self.fixups.append((pos, label, 4))

    def rel8(self, label: str) -> None:
        pos = len(self.buf)
        self.emit(0)
        self.fixups.append((pos, label, 1))

    def fix(self) -> None:
        for pos, label, size in self.fixups:
            val = self.labels[label] - (pos + size)
            if size == 1:
                self.buf[pos] = val & 0xFF
            else:
                self.buf[pos : pos + 4] = le32(val)


def gen(op: str) -> bytes:
    a = Asm(BASE + HEADER)
    a.L("_start")
    a.emit(0x48, 0x8B, 0x74, 0x24, 0x10)
    a.emit(0xE8)
    a.rel32("atoi")
    a.emit(0x48, 0x63, 0xC0)
    a.emit(0x49, 0x89, 0xC4)
    monad = op in ("halve", "neg", "abs")
    if not monad:
        a.emit(0x48, 0x8B, 0x74, 0x24, 0x18)
        a.emit(0xE8)
        a.rel32("atoi")
        a.emit(0x48, 0x63, 0xC0)
        a.emit(0x49, 0x89, 0xC5)
    ops_emit = {
        "mul": [0x4D, 0x0F, 0xAF, 0xE5],
        "add": [0x4D, 0x01, 0xEC],
        "sub": [0x4D, 0x29, 0xEC],
        "div": [0x4C, 0x89, 0xE0, 0x48, 0x99, 0x49, 0xF7, 0xFD, 0x49, 0x89, 0xC4],
        "mod": [0x4C, 0x89, 0xE0, 0x48, 0x99, 0x49, 0xF7, 0xFD, 0x49, 0x89, 0xD4],
        "halve": [0x49, 0xC1, 0xFC, 0x01],
        "neg": [0x49, 0xF7, 0xDC],
        "abs": [0x4D, 0x85, 0xE4, 0x79, 0x03, 0x49, 0xF7, 0xDC],
    }
    if op == "pow":
        a.emit(0xB8, 0x01, 0x00, 0x00, 0x00)
        a.L("powloop")
        a.emit(0x4D, 0x85, 0xED)
        a.emit(0x74)
        a.rel8("powdone")
        a.emit(0x49, 0x0F, 0xAF, 0xC4)
        a.emit(0x49, 0xFF, 0xCD)
        a.emit(0xEB)
        a.rel8("powloop")
        a.L("powdone")
        a.emit(0x49, 0x89, 0xC4)
    else:
        a.emit(*ops_emit[op])
    a.emit(0x4C, 0x89, 0xE7)
    a.emit(0xE8)
    a.rel32("putnum")
    a.emit(0xB8, 0x3C, 0x00, 0x00, 0x00, 0x31, 0xFF, 0x0F, 0x05)

    a.L("atoi")
    a.emit(0x31, 0xC0, 0x31, 0xD2, 0x0F, 0xB6, 0x0E, 0x83, 0xF9, 0x2D)
    a.emit(0x75)
    a.rel8("atoiloop")
    a.emit(0x48, 0xFF, 0xC6, 0xBA, 0x01, 0x00, 0x00, 0x00)
    a.L("atoiloop")
    a.emit(0x0F, 0xB6, 0x0E, 0x85, 0xC9)
    a.emit(0x74)
    a.rel8("atoidone")
    a.emit(0x83, 0xF9, 0x30)
    a.emit(0x7C)
    a.rel8("atoidone")
    a.emit(0x83, 0xF9, 0x39)
    a.emit(0x7F)
    a.rel8("atoidone")
    a.emit(0x6B, 0xC0, 0x0A, 0x83, 0xE9, 0x30, 0x01, 0xC8, 0x48, 0xFF, 0xC6)
    a.emit(0xEB)
    a.rel8("atoiloop")
    a.L("atoidone")
    a.emit(0x85, 0xD2)
    a.emit(0x74)
    a.rel8("atoiret")
    a.emit(0xF7, 0xD8)
    a.L("atoiret")
    a.emit(0xC3)

    a.L("putnum")
    a.emit(0x48, 0x89, 0xFB, 0x48, 0x83, 0xEC, 0x40, 0x48, 0x8D, 0x6C, 0x24, 0x3F)
    a.emit(0xC6, 0x45, 0x00, 0x0A, 0x41, 0xB8, 0x01, 0x00, 0x00, 0x00)
    a.emit(0x48, 0x89, 0xD8, 0x48, 0x85, 0xC0)
    a.emit(0x79)
    a.rel8("pnpos")
    a.emit(0x48, 0xF7, 0xD8, 0x41, 0xB9, 0x01, 0x00, 0x00, 0x00)
    a.emit(0xEB)
    a.rel8("pnconv")
    a.L("pnpos")
    a.emit(0x45, 0x31, 0xC9)
    a.L("pnconv")
    a.emit(0x48, 0x85, 0xC0)
    a.emit(0x75)
    a.rel8("pnloop")
    a.emit(0x48, 0xFF, 0xCD, 0xC6, 0x45, 0x00, 0x30, 0x49, 0xFF, 0xC0)
    a.emit(0xEB)
    a.rel8("pnsign")
    a.L("pnloop")
    a.emit(0x48, 0x85, 0xC0)
    a.emit(0x74)
    a.rel8("pnsign")
    a.emit(0x48, 0x31, 0xD2, 0x48, 0xB9, 0x0A, 0, 0, 0, 0, 0, 0, 0, 0x48, 0xF7, 0xF1)
    a.emit(0x80, 0xC2, 0x30, 0x48, 0xFF, 0xCD, 0x88, 0x55, 0x00, 0x49, 0xFF, 0xC0)
    a.emit(0xEB)
    a.rel8("pnloop")
    a.L("pnsign")
    a.emit(0x45, 0x85, 0xC9)
    a.emit(0x74)
    a.rel8("pnwrite")
    a.emit(0x48, 0xFF, 0xCD, 0xC6, 0x45, 0x00, 0x2D, 0x49, 0xFF, 0xC0)
    a.L("pnwrite")
    a.emit(0xB8, 0x01, 0x00, 0x00, 0x00, 0xBF, 0x01, 0x00, 0x00, 0x00)
    a.emit(0x48, 0x89, 0xEE, 0x4C, 0x89, 0xC2, 0x0F, 0x05)
    a.emit(0x48, 0x83, 0xC4, 0x40, 0xC3)
    a.fix()
    return bytes(a.buf)


def main() -> None:
    ops = [
        ("H", "halve"),
        ("N", "neg"),
        ("A", "abs"),
        ("+", "add"),
        ("×", "mul"),
        ("÷", "div"),
        ("-", "sub"),
        ("%", "mod"),
        ("*", "pow"),
    ]
    table = [build_elf(gen(op)) for _, op in ops]
    table_lit = "[" + ",".join("[" + ",".join(map(str, elf)) + "]" for elf in table) + "]"
    main_link = "³Ḣµ“HNA+×÷-%*”iµị¢"
    OUT.write_text(table_lit + "\n" + main_link + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(table)} ELF blobs)")


if __name__ == "__main__":
    main()
