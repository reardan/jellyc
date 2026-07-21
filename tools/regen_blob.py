#!/usr/bin/env python3
"""Assemble src/runtime/runtime.s into the runtime blob and its symbol map.

Dev-time tool (needs binutils: as, ld, objcopy, nm). Produces:
  build/blob.bin      raw machine-code blob, loaded at RT_BASE
  build/blob.syms     "name offset" lines (offset from blob start)

The bootstrap itself never runs this - the blob bytes are embedded in the
Jelly compiler source as a checked-in literal (M4). This tool regenerates
that literal so the runtime can be edited in real assembly.

Layout constant RT_BASE must match ref/jellyc.py's ELF layout.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "runtime", "runtime.s")
BUILD = os.path.join(ROOT, "build")
RT_BASE = 0x400100


def run(*cmd):
    subprocess.run(cmd, check=True)


def main():
    os.makedirs(BUILD, exist_ok=True)
    obj = os.path.join(BUILD, "runtime.o")
    elf = os.path.join(BUILD, "runtime.elf")
    binp = os.path.join(BUILD, "blob.bin")
    syms = os.path.join(BUILD, "blob.syms")

    run("as", "-o", obj, SRC)
    # Link at RT_BASE so symbol addresses are RT_BASE + offset; _start first.
    run("ld", "-e", "_start", f"--section-start=.text={RT_BASE:#x}",
        "-o", elf, obj)
    run("objcopy", "-O", "binary", "--only-section=.text", elf, binp)

    nm = subprocess.run(["nm", elf], check=True, capture_output=True, text=True)
    lines = []
    for row in nm.stdout.splitlines():
        parts = row.split()
        if len(parts) != 3:
            continue
        addr, kind, name = parts
        if name.startswith("rt_") or name in ("_start", "main_ptr"):
            lines.append(f"{name} {int(addr, 16) - RT_BASE}")
    open(syms, "w").write("\n".join(sorted(lines)) + "\n")

    size = os.path.getsize(binp)
    print(f"blob.bin: {size} bytes at {RT_BASE:#x}")
    print(open(syms).read().strip())


if __name__ == "__main__":
    main()
