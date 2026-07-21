#!/usr/bin/env python3
"""Differential test runner.

For each case, compare byte-for-byte:
  leg A: the reference interpreter (stage0 semantics), via bootstrap/stage0.py
  leg B: the ref/jellyc.py-compiled native ELF
and, when a self-hosted compiler is provided via JELLYC_SELF, also:
  leg C: the JELLYC_SELF-compiled native ELF   (M5)

A case is a directory tests/cases/NAME/ with:
  prog.jelly    the JellyCore program (UTF-8, newline-separated links)
  in            stdin bytes (optional; empty if absent)

usage: tests/run.py [NAME ...]     (default: all cases)
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CASES = os.path.join(HERE, "cases")
BUILD = os.path.join(ROOT, "build", "t")


def interp(prog, data):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "bootstrap", "stage0.py"), prog],
                       input=data, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("interpreter failed: " + p.stderr.decode(errors="replace"))
    return p.stdout


def compile_and_run(compiler_argv, prog, data, out_elf):
    c = subprocess.run(compiler_argv + [prog, out_elf], capture_output=True)
    if c.returncode != 0:
        raise RuntimeError("compile failed: " + c.stderr.decode(errors="replace"))
    r = subprocess.run([out_elf], input=data, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"binary exited {r.returncode}: "
                           + r.stderr.decode(errors="replace"))
    return r.stdout


def main():
    names = sys.argv[1:] or sorted(
        os.path.basename(os.path.dirname(p))
        for p in glob.glob(os.path.join(CASES, "*", "prog.jelly")))
    os.makedirs(BUILD, exist_ok=True)
    ref_argv = [sys.executable, os.path.join(ROOT, "ref", "jellyc.py")]
    self_c = os.environ.get("JELLYC_SELF")
    fails = 0
    for name in names:
        d = os.path.join(CASES, name)
        prog = os.path.join(d, "prog.jelly")
        in_path = os.path.join(d, "in")
        data = open(in_path, "rb").read() if os.path.exists(in_path) else b""
        try:
            a = interp(prog, data)
            b = compile_and_run(ref_argv, prog, data, os.path.join(BUILD, name + ".ref"))
            legs = {"interp": a, "ref": b}
            if self_c:
                c = compile_and_run([self_c], prog, data, os.path.join(BUILD, name + ".self"))
                legs["self"] = c
            uniq = set(legs.values())
            if len(uniq) == 1:
                print(f"ok   {name}")
            else:
                fails += 1
                print(f"FAIL {name}: " + ", ".join(
                    f"{k}={list(v)}" for k, v in legs.items()))
        except Exception as e:
            fails += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(names) - fails}/{len(names)} cases passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
