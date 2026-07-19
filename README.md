# jellyc

**A Jelly → x86-64 ELF compiler, written in Jelly.**

Compiles a subset of [Dennis Mitchell's Jelly](https://github.com/DennisMitchell/jellylanguage)
to a static Linux **x86-64 ELF**. The compiler itself is the Jelly program
`jellyc.jelly`, bootstrapped by the official `jelly` interpreter.

```sh
pip3 install --user jellylanguage
export PATH="$HOME/.local/bin:$PATH"

./jellyc -o mul '×'
./mul 14 3          # 42

./jellyc -r 'H' 10  # 5
file mul            # ELF 64-bit LSB executable, x86-64, statically linked
```

## How it works

| Piece | Role |
|-------|------|
| `jellyc.jelly` | Compiler in Jelly: table of full ELF blobs + atom lookup (`ị`) |
| `jellyc` | Driver: runs `jelly fu jellyc.jelly`, packs the byte list to a file |
| official `jelly` | Bootstrap runtime |

`jellyc.jelly` is two links:

1. A niladic table — nine prebuilt x86-64 ELF images (one per supported atom)  
2. `³Ḣµ“HNA+×÷-%*”iµị¢` — take the program atom, index the table, return the byte list  

Each ELF is a tiny freestanding program: parse `argv` with an inlined `atoi`,
apply the op, `write` the decimal result, `exit`. No libc.

> Jelly’s `Ọ` UTF-8-encodes bytes ≥ 128, so the driver packs the printed
> byte list into binary. All **codegen** lives in Jelly.

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

## Test

```sh
make test
```

## Regenerate ELF table

The blobs inside `jellyc.jelly` are produced by `tools/gen_jellyc.py`
(hand-assembled x64). Users only need `jelly` + `./jellyc`.

## Heritage

Language / bootstrap: [DennisMitchell/jellylanguage](https://github.com/DennisMitchell/jellylanguage) (MIT).
