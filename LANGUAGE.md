# Jelly Language

Jelly is a tiny systems language designed so its compiler can be written in
Jelly itself. The first edition is intentionally small: enough to implement
`jellyc`, emit a Linux x86 ELF binary, and reach a self-hosting fixpoint.

## Hello

```c
/* examples/hello.jelly */
int putchar(int);

int main()
{
  putchar('H');
  putchar('i');
  putchar(10);
  return 0;
}
```

```sh
bin/jellyc < examples/hello.jelly > bin/hello
chmod +x bin/hello
./bin/hello
```

## Surface syntax

Jelly looks like a small subset of C:

- Types: `int`, `char`, and pointers (`char *`, `int *`, ...)
- Functions and globals
- Locals with optional initializers
- `if` / `else`, `while`, `return`
- Operators: `+ - << >> <= < >= > == != & | =` and indexing `[]`
- Character and string literals (`'\n'`, `"hi"`, `"\x0a"`)
- Comments: `/* ... */` and `#` to end of line

There is no preprocessor, no `struct`, no `for`, and almost no error
recovery. Invalid programs may fail at compile time with exit status 1, or
produce a binary that crashes.

## Runtime

Generated binaries are static 32-bit x86 ELF images with a single RWX
load segment. They include tiny implementations of:

| Symbol   | Role                                      |
|----------|-------------------------------------------|
| `exit`   | terminate with status                     |
| `getchar`| read one byte from stdin (−1 on EOF)      |
| `putchar`| write one byte to stdout                  |
| `malloc` | bump allocator via `brk` (no `free`)      |

No libc is linked. `main` must be the first function defined in a program
(the ELF entry jumps to the first definition).

## Compilation model

`jellyc` is a single-pass, syntax-directed compiler in the spirit of
Edmund Grimley Evans' `cc500`: parse and emit machine code together, with
no AST and no IR. The compiler reads a complete Jelly program from stdin
and writes an ELF binary to stdout.
