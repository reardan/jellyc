#!/usr/bin/env python3
"""M2 gate: the runtime blob produces a clean, syscall-minimal, binary-safe
executable. Builds the identity ('echo') program via the reference backend and
exercises it directly, independent of the differential suite.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ref"))
import jellyc

BUILD = os.path.join(ROOT, "build", "t")
os.makedirs(BUILD, exist_ok=True)
fails = []


def expect(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL:", msg)


echo = os.path.join(BUILD, "echo")
with open(echo, "wb") as f:
    f.write(jellyc.compile_program("⁸"))
os.chmod(echo, 0o755)

# 1. byte-exactness across all 256 byte values, repeated
data = bytes(range(256)) * 137
r = subprocess.run([echo], input=data, capture_output=True)
expect(r.returncode == 0, f"echo exit {r.returncode}")
expect(r.stdout == data, "echo not byte-exact on 256-value stress")

# 2. empty input -> empty output, clean exit
r = subprocess.run([echo], input=b"", capture_output=True)
expect(r.returncode == 0 and r.stdout == b"", "empty input handling")

# 3. ELF is well-formed (readelf, if available)
if shutil.which("readelf"):
    r = subprocess.run(["readelf", "-hl", echo], capture_output=True, text=True)
    expect(r.returncode == 0, "readelf rejected the ELF")
    expect("EXEC" in r.stdout and "x86-64" in r.stdout.replace("X86-64", "x86-64"),
           "ELF header not ET_EXEC/x86-64")
    expect("LOAD" in r.stdout, "no PT_LOAD segment")

# 4. syscall hygiene: only mmap/read/write/exit (strace, if available)
if shutil.which("strace"):
    r = subprocess.run(["strace", "-f", "-e", "trace=%process,%memory,read,write",
                        echo], input="hi", capture_output=True, text=True)
    allowed = ("mmap", "read", "write", "exit_group", "exit", "execve",
               "arch_prctl", "brk", "+++", "---")
    for line in r.stderr.splitlines():
        name = line.split("(")[0].strip()
        if not name or name.startswith(("+++", "---")):
            continue
        expect(any(name.startswith(a) for a in allowed),
               f"unexpected syscall: {name}")

if fails:
    print(f"\n{len(fails)} runtime test(s) FAILED")
    sys.exit(1)
print("all runtime tests passed")
