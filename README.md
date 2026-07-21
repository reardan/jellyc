# jellyc

A self-hosting compiler for [Jelly](https://github.com/DennisMitchell/jellylanguage),
written in Jelly, in the spirit of
[cc500](https://homepage.ntlworld.com/edmund.grimley-evans/cc500.html) — Edmund
Grimley Evans' ~600-line C compiler that compiles itself and emits an ELF
executable directly, with no assembler, linker, or libc.

cc500's trick is that it does not compile *all* of C — it compiles a subset,
and is written in that subset. jellyc does the same for Jelly: it compiles
**JellyCore** (a subset with a fixed token set and no depth-based
vectorization, see [SPEC.md](SPEC.md)) and is itself written strictly inside
JellyCore. The identical source runs under the reference Python interpreter
*and* under its own compiled output; self-hosting is proven by the bootstrap
fixpoint `stage2 == stage3`, byte-for-byte.

Targets **x86-64 Linux**: the compiler writes machine-code bytes and the ELF
header itself and talks to the kernel through raw syscalls. Compiled programs
are filters — stdin bytes in, stdout bytes out (see
[SPEC.md](SPEC.md#io-convention)).

## Status

This is an in-progress build. The pipeline is proven end-to-end on a growing
slice of the language:

| Milestone | State |
| --- | --- |
| **M0** stage0 interpreter harness + semantic probes | ✅ done |
| **M1** frozen JellyCore spec + subset checker | ✅ done |
| **M2** x86-64 runtime blob (syscalls, bump heap, list ops) | ✅ done |
| **M3** reference compiler (`ref/jellyc.py`) + differential tests | 🚧 vertical slice working; growing atom/modifier coverage |
| **M4** transliterate the compiler into Jelly (`src/jellyc.d/`) | ⏳ next |
| **M5** self-host fixpoint | ⏳ |
| **M6** CI + docs | 🚧 |

Today, `ref/jellyc.py` compiles JellyCore programs using `⁸ ⁹ ³ ⁴ ⁵`, integer
and list literals, the monads `L Ṛ ‘ ’ ¹`, the dyads `; +`, the `€` map, and
`Ç ç ¢` link calls, through the full tokenizer → chain-rule → x86-64 → ELF
path, and every case in `tests/cases/` produces byte-identical output to the
reference interpreter. Remaining atoms/modifiers plug into the same machinery.

## Layout

```
SPEC.md                the frozen JellyCore contract
ref/jellyc.py          reference compiler: tokenizer, checker, codegen, ELF
src/runtime/runtime.s  x86-64 runtime blob (assembled once, dev-time)
bootstrap/stage0.py    interpreter harness with the bytes-in/bytes-out ABI
tools/                 vendoring, codepage transcode, probes, blob regen
tests/                 differential runner + cases, checker/runtime unit tests
build/blob.bin,.syms   checked-in assembled runtime + symbol map
vendor/                the pinned reference interpreter (fetched, gitignored)
```

## Quickstart

```bash
tools/vendor.sh              # fetch the pinned reference interpreter (+ sympy)
python3 tools/probes.py      # confirm interpreter semantics jellyc relies on
python3 tools/regen_blob.py  # (re)assemble the runtime blob   [needs binutils]

# compile a JellyCore program to a native executable and run it
printf 'Ṛ' > /tmp/rev.jelly
python3 ref/jellyc.py /tmp/rev.jelly /tmp/rev && echo -n 'abc' | /tmp/rev   # -> cba

python3 tests/run.py         # differential suite: interpreter vs compiled
sh tools/ci.sh               # or: the whole gate in one shot
```

## How it works

- **Values** are 64-bit tagged words: `int v → (v<<1)|1`, list → pointer to a
  bump-allocated `{length, elems...}` object (never freed, like cc500).
- **Runtime** (`src/runtime/runtime.s`) is a small position-relocatable blob:
  `_start` maps a heap arena, slurps stdin into a tagged byte list, calls the
  main link, deep-flattens the result to stdout, and exits — using only
  `mmap`/`read`/`write`/`exit`.
- **Codegen** replays Jelly's chain rules at compile time, lowering each link
  to a straight-line push/call sequence. Runtime calls are absolute-indirect
  and loops are intra-fragment relative, so there is **no backpatching**; `Ç`
  link calls are backward-only, so every address is known when it is emitted.
  See [docs/codegen.md](docs/codegen.md).
- **Bootstrap** (planned M4–M5): the Python interpreter runs the Jelly compiler
  on itself to make `stage1`; `stage1` compiles itself to `stage2`; `stage2` to
  `stage3`; `stage2 == stage3` is the self-hosting proof.
