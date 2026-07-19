# jellyc

**A Jelly compiler, written in Jelly.**

This is a compiler for [Dennis Mitchell's Jelly](https://github.com/DennisMitchell/jellylanguage)
whose compiler source is itself a Jelly program (`jellyc.jelly`). It runs on the
official Jelly interpreter and emits Python.

```sh
pip3 install --user jellylanguage   # https://github.com/DennisMitchell/jellylanguage
export PATH="$HOME/.local/bin:$PATH"

./jellyc -r '×' 14 3                # 42
./jellyc -r 'H' 10                  # 5.0
./jellyc '+'                        # print a Python program
```

## How it works

| Piece | Role |
|-------|------|
| `jellyc.jelly` | The compiler — a Jelly program (atom → Python expression table) |
| `jellyc` | Thin shell driver: scaffolds a Python program around that expression and optionally runs it |
| official `jelly` | Bootstrap runtime that executes `jellyc.jelly` |

`jellyc.jelly` is two links of Jelly:

```jelly
“a/2“-a“abs(a)“a+b“a*b“a//b“a-b“a%b“a**b
³Ḣµ“HNA+×÷-%*”iµị¢
```

1. A niladic table of Python expression fragments  
2. Take the program atom from `³`, find it in `HNA+×÷-%*`, index into the table

That is the whole compiler core — no C, no invented curly-brace language.

## Supported subset

Single-atom programs:

| Jelly | Python | Arity |
|-------|--------|-------|
| `H` | `a/2` | monad |
| `N` | `-a` | monad |
| `A` | `abs(a)` | monad |
| `+` | `a+b` | dyad |
| `×` | `a*b` | dyad |
| `÷` | `a//b` | dyad |
| `-` | `a-b` | dyad |
| `%` | `a%b` | dyad |
| `*` | `a**b` | dyad |

## CLI

```text
jellyc <code>                 emit Python program
jellyc -e <code>              emit expression only
jellyc -r <code> [args...]    compile and run
jellyc -f <file>              compile a .jelly file
jellyc -fr <file> [args...]   compile file and run
```

## Test

```sh
make test
```

## Heritage

Language and bootstrap interpreter: [DennisMitchell/jellylanguage](https://github.com/DennisMitchell/jellylanguage) (MIT).
This repo is a separate compiler project that targets that language and is
implemented in it.
