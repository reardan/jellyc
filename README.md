# jellyc

**A Jelly → x86-64 ELF compiler, written in Jelly.**

Compiles a subset of [Dennis Mitchell's Jelly](https://github.com/DennisMitchell/jellylanguage)
to a static Linux **x86-64 ELF**. The compiler logic is Jelly (`jellyc.jelly` +
`elf.jelly`); `bin/jellyc1` is a freestanding native stage-1 with the same output.

```sh
pip3 install --user jellylanguage
export PATH="$HOME/.local/bin:$PATH"
make gen          # elf.jelly + bin/jellyc1

./jellyc -o mul '×'
./mul 14 3          # 42

./jellyc -r 'H' 10  # 5
file mul            # ELF 64-bit LSB executable, x86-64
```

## How it works

| Piece | Role |
|-------|------|
| `elf.jelly` | x64 ELF codegen data — nine prebuilt freestanding ELF images |
| `jellyc.jelly` | Compiler logic — atom → blob lookup (`³Ḣµ“HNA+×÷-%*”iµị¢`) |
| `bin/jellyc1` | Freestanding native stage-1 (no `jelly` at runtime) |
| `jellyc` | Driver: prefers `jellyc1`, else runs Jelly + packs bytes |
| `elf_hdr.jelly` | Seed helpers for compositional ELF headers (`b256U`, magic) |
| official `jelly` | Bootstrap runtime for the Jelly backend |

Jelly has no imports, so the Jelly backend runs `elf.jelly` + `jellyc.jelly` as
one program (table link, then lookup link; `¢` reads the table above).

Each program ELF is freestanding: inlined `atoi`, op, `write` decimal, `exit`.

> Jelly’s `Ọ` UTF-8-encodes bytes ≥ 128, so the Jelly backend packs the printed
> byte list in the driver. The native backend writes ELF bytes directly.

## Bootstrap

```sh
make bootstrap   # gen + prove jelly ≡ jellyc1 for every supported atom
```

`bin/jellyc1` is the first rung toward self-host: it emits the same ELFs without
the interpreter. True self-host (compiling `jellyc.jelly` itself to a fixpoint)
still needs a larger subset and compositional codegen.

## Supported subset

| Jelly | x64 op | Arity |
|-------|--------|-------|
| `H` | `sar` / 2 | monad |
| `N` | `neg` | monad |
| `A` | conditional `neg` | monad |
| `+` | `add` | dyad |
| `×` | `imul` | dyad |
| `÷` | `idiv` quotient | dyad |
| `-` | `sub` | dyad |
| `%` | `idiv` remainder | dyad |
| `*` | integer power loop | dyad |

## CLI

```text
jellyc <code>                 ELF to stdout
jellyc -o <file> <code>       ELF to file (+x)
jellyc -r <code> [args...]    compile and run
jellyc -f / -fo / -fr         same with a .jelly source file
```

`JELLYC_BACKEND=native|jelly|auto` selects the compiler backend (default `auto`).

## Test

```sh
make test
```

## Regenerate

```sh
make gen    # tools/gen_jellyc.py → elf.jelly, jellyc.jelly, bin/jellyc1
```

## Heritage

Language / bootstrap: [DennisMitchell/jellylanguage](https://github.com/DennisMitchell/jellylanguage) (MIT).
