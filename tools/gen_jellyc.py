#!/usr/bin/env python3
"""Generate Jelly compiler sources and the freestanding stage-1 native jellyc.

Writes:
  elf.jelly       — table of x86-64 ELF blobs (Jelly data link)
  jellyc.jelly    — atom → blob lookup (Jelly main link)
  bin/jellyc1     — freestanding native compiler (no `jelly` needed at runtime)

Stage-0 is this script + the official Jelly interpreter.
Self-host goal: bin/jellyc1 (and later stages) compile the Jelly sources
without this Python generator.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ELF_OUT = ROOT / "elf.jelly"
COMPILER_OUT = ROOT / "jellyc.jelly"
NATIVE_OUT = ROOT / "bin" / "jellyc1"

BASE = 0x400000
HEADER = 120
ATOMS = ["H", "N", "A", "+", "×", "÷", "-", "%", "*"]
OP_NAMES = {
    "H": "halve",
    "N": "neg",
    "A": "abs",
    "+": "add",
    "×": "mul",
    "÷": "div",
    "-": "sub",
    "%": "mod",
    "*": "pow",
}


def le16(x: int) -> bytes:
    return struct.pack("<H", x & 0xFFFF)


def le32(x: int) -> bytes:
    return struct.pack("<I", x & 0xFFFFFFFF)


def le64(x: int) -> bytes:
    return struct.pack("<Q", x & 0xFFFFFFFFFFFFFFFF)


def build_elf(code: bytes) -> bytes:
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
    return bytes(e + p + code)


class Asm:
    def __init__(self, org: int) -> None:
        self.org = org
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, int]] = []
        self.abs64: list[tuple[int, str]] = []  # (pos, label) movabs patches

    def L(self, name: str) -> None:
        self.labels[name] = len(self.buf)

    def here(self) -> int:
        return len(self.buf)

    def emit(self, *bs: int) -> None:
        for b in bs:
            self.buf.append(b & 0xFF)

    def emit_bytes(self, data: bytes) -> None:
        self.buf.extend(data)

    def rel32(self, label: str) -> None:
        pos = self.here()
        self.emit(0, 0, 0, 0)
        self.fixups.append((pos, label, 4))

    def rel8(self, label: str) -> None:
        pos = self.here()
        self.emit(0)
        self.fixups.append((pos, label, 1))

    def movabs_r12(self, label: str) -> None:
        self.emit(0x49, 0xBC)  # mov r12, imm64
        pos = self.here()
        self.emit(*[0] * 8)
        self.abs64.append((pos, label))

    def fix(self) -> None:
        for pos, label, size in self.fixups:
            val = self.labels[label] - (pos + size)
            if size == 1:
                self.buf[pos] = val & 0xFF
            else:
                self.buf[pos : pos + 4] = le32(val)
        for pos, label in self.abs64:
            addr = self.org + self.labels[label]
            self.buf[pos : pos + 8] = le64(addr)


def gen_op_code(op: str) -> bytes:
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


def build_native_compiler(blobs: list[bytes]) -> bytes:
    """Freestanding jellyc1: argv[1] selects a blob; write(1, blob, len); exit.

    Atom table entry (24 bytes):
      +0  u64  VA of NUL-terminated UTF-8 atom string
      +8  u64  VA of blob
      +16 u32  blob length
      +20 u32  pad
    """
    assert len(blobs) == 9
    ENTRY = 24
    a = Asm(BASE + HEADER)

    a.L("_start")
    a.emit(0x48, 0x83, 0x3C, 0x24, 0x02)  # cmp qword [rsp], 2
    a.emit(0x0F, 0x8C)
    a.rel32("fail")
    a.emit(0x4C, 0x8B, 0x7C, 0x24, 0x10)  # r15 = argv[1]
    a.emit(0x4D, 0x85, 0xFF)
    a.emit(0x0F, 0x84)
    a.rel32("fail")

    a.movabs_r12("atom_table")
    a.emit(0x45, 0x31, 0xF6)  # r14d = 0  (index; avoids clobbering)

    a.L("find")
    a.emit(0x41, 0x83, 0xFE, 0x09)  # cmp r14d, 9
    a.emit(0x0F, 0x8D)
    a.rel32("fail")

    # rbx = r12 + r14*24
    a.emit(0x4C, 0x89, 0xE3)  # mov rbx, r12
    a.emit(0x49, 0x63, 0xC6)  # movsxd rax, r14d
    a.emit(0x48, 0x89, 0xC2)  # mov rdx, rax
    a.emit(0x48, 0xC1, 0xE0, 0x04)  # shl rax, 4
    a.emit(0x48, 0xC1, 0xE2, 0x03)  # shl rdx, 3
    a.emit(0x48, 0x01, 0xD0)  # add rax, rdx  (= *24)
    a.emit(0x48, 0x01, 0xC3)  # add rbx, rax

    a.emit(0x48, 0x8B, 0x3B)  # rdi = [rbx] atom string
    a.emit(0x31, 0xD2)  # edx = 0

    a.L("cmpb")
    a.emit(0x41, 0x0F, 0xB6, 0x04, 0x17)  # movzx eax, byte [r15+rdx]
    a.emit(0x44, 0x0F, 0xB6, 0x04, 0x17)  # movzx r8d, byte [rdi+rdx]
    a.emit(0x44, 0x38, 0xC0)  # cmp al, r8b
    a.emit(0x0F, 0x85)
    a.rel32("next")
    a.emit(0x84, 0xC0)  # test al, al
    a.emit(0x74)
    a.rel8("matched")
    a.emit(0xFF, 0xC2)  # inc edx
    a.emit(0xEB)
    a.rel8("cmpb")

    a.L("matched")
    a.emit(0x48, 0x8B, 0x73, 0x08)  # rsi = [rbx+8] blob VA
    a.emit(0x8B, 0x53, 0x10)  # edx = [rbx+16] length
    a.emit(0xB8, 0x01, 0x00, 0x00, 0x00)  # write
    a.emit(0xBF, 0x01, 0x00, 0x00, 0x00)
    a.emit(0x0F, 0x05)
    a.emit(0xB8, 0x3C, 0x00, 0x00, 0x00)  # exit(0)
    a.emit(0x31, 0xFF)
    a.emit(0x0F, 0x05)

    a.L("next")
    a.emit(0x41, 0xFF, 0xC6)  # inc r14d
    a.emit(0xE9)
    a.rel32("find")

    a.L("fail")
    a.emit(0xB8, 0x3C, 0x00, 0x00, 0x00)
    a.emit(0xBF, 0x01, 0x00, 0x00, 0x00)
    a.emit(0x0F, 0x05)

    # --- data: atom strings, blobs, then table ---
    atom_str_labels: list[str] = []
    for i, atom in enumerate(ATOMS):
        name = f"atom_str_{i}"
        atom_str_labels.append(name)
        a.L(name)
        a.emit_bytes(atom.encode("utf-8") + b"\0")

    blob_labels: list[str] = []
    for i, blob in enumerate(blobs):
        name = f"blob_{i}"
        blob_labels.append(name)
        a.L(name)
        a.emit_bytes(blob)

    a.L("atom_table")
    table_pos = a.here()
    # Placeholder 24*9 bytes; patch VAs after fix() needs labels resolved —
    # emit zeros then poke absolute VAs using org+label.
    a.emit(*[0] * (ENTRY * 9))

    # Resolve code relocs first so labels are final, then fill table.
    a.fix()
    for i in range(9):
        ent = table_pos + i * ENTRY
        a.buf[ent : ent + 8] = le64(a.org + a.labels[atom_str_labels[i]])
        a.buf[ent + 8 : ent + 16] = le64(a.org + a.labels[blob_labels[i]])
        a.buf[ent + 16 : ent + 20] = le32(len(blobs[i]))

    return build_elf(bytes(a.buf))


def write_jelly_sources(blobs: list[bytes]) -> None:
    table_lit = (
        "["
        + ",".join("[" + ",".join(map(str, blob)) + "]" for blob in blobs)
        + "]"
    )
    main_link = "³Ḣµ“HNA+×÷-%*”iµị¢"
    ELF_OUT.write_text(table_lit + "\n", encoding="utf-8")
    COMPILER_OUT.write_text(main_link + "\n", encoding="utf-8")


def write_compositional_helpers() -> None:
    """Jelly helpers toward building ELF bytes without opaque full-program blobs.

    `elf_hdr.jelly` links (via ³ / nilad):
      1) le bytes — `³b256U` (base-256 digits, reversed → little-endian)
      2) same (le16 callers truncate)
      3) magic — 7F 45 4C 46
    Padding short integers to fixed width is still open; blobs remain authoritative.
    """
    path = ROOT / "elf_hdr.jelly"
    path.write_text("³b256U\n³b256U\n127,69,76,70\n", encoding="utf-8")


def main() -> None:
    blobs = [build_elf(gen_op_code(OP_NAMES[atom])) for atom in ATOMS]
    write_jelly_sources(blobs)
    print(f"wrote {ELF_OUT.name} ({ELF_OUT.stat().st_size} bytes, {len(blobs)} blobs)")
    print(f"wrote {COMPILER_OUT.name}")

    NATIVE_OUT.parent.mkdir(parents=True, exist_ok=True)
    native = build_native_compiler(blobs)
    NATIVE_OUT.write_bytes(native)
    NATIVE_OUT.chmod(0o755)
    print(f"wrote {NATIVE_OUT} ({len(native)} bytes) — freestanding stage-1")

    write_compositional_helpers()
    print("wrote elf_hdr.jelly (helper seed)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        raise
