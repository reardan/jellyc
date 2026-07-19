# jellyc

**Jelly compiler, written in Jelly.**

Jelly is a tiny self-hosting systems language. `jellyc` reads Jelly source
from stdin and writes a 32-bit Linux x86 ELF binary to stdout. The compiler
is itself a Jelly program (`jellyc.jelly`), so once bootstrapped it compiles
itself to a fixpoint.

```sh
make          # gcc bootstrap -> bin/jellyc0, then self-compile -> bin/jellyc
make verify   # prove self-host: stage2 binary == stage3 binary
make test     # compile and run examples/
```

```sh
bin/jellyc < examples/hello.jelly > bin/hello
chmod +x bin/hello
./bin/hello
# Hello, Jelly!
```

## Why Jelly

Jelly sits in the `cc500` tradition: a language small enough that its compiler
fits in one file, emits machine code directly (no AST, no IR, no libc), and
can compile itself. The language surface is a C subset so a stock C compiler
can provide stage 0; after that, Jelly owns the toolchain.

See [LANGUAGE.md](LANGUAGE.md) for syntax and runtime details.

## Layout

| Path | Role |
|------|------|
| `jellyc.jelly` | The Jelly compiler (source of truth) |
| `examples/` | Sample Jelly programs |
| `tests/expected/` | Golden outputs for `make test` |
| `LANGUAGE.md` | Language reference |
| `Makefile` | Bootstrap, verify, test |

## Bootstrap chain

```
gcc -x c jellyc.jelly   -> bin/jellyc0   (stage 0, host)
bin/jellyc0 < jellyc.jelly -> bin/jellyc1
bin/jellyc1 < jellyc.jelly -> bin/jellyc2
bin/jellyc2 < jellyc.jelly -> bin/jellyc3
cmp bin/jellyc2 bin/jellyc3              # fixpoint
```

## Requirements

- Linux x86_64 host (runs 32-bit static ELF without multilib)
- `gcc` for stage 0 only

## Heritage

Code generation and the self-hosting subset follow Edmund Grimley Evans'
[cc500](http://homepage.ntlworld.com/edmund.grimley-evans/cc500/). Jelly
adds `#` line comments, the full relational set (`< > <= >=`), and the
language/docs packaging around a Jelly-first workflow. Licensed under
GPL-2.0 (see `LICENSE`).
