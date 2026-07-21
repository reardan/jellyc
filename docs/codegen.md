# jellyc codegen

How JellyCore lowers to x86-64. This documents `ref/jellyc.py`; the Jelly
compiler (`src/jellyc.d/`, M4) mirrors it link-for-link.

## Value representation

64-bit tagged words, matching `src/runtime/runtime.s`:

- **int** `v` → `(v << 1) | 1` — low bit 1, a signed 63-bit value.
- **list** → an 8-byte-aligned pointer (low bit 0) to a heap object
  `[ int64 length ][ word elem_0 ] … [ word elem_{n-1} ]`.

Untag an int with an arithmetic shift right by 1; tag with `(x<<1)|1`.
Increment/decrement are just `+2`/`-2` on the tagged word.

## Calling convention

- A **link** is a function:
  `push r12; push r13; mov r12,rdi; mov r13,rsi; <body → rax>; pop r13; pop r12; ret`.
  `r12`/`r13` hold the link's own left/right arguments for the whole body.
- A **fragment** computes into `rax`. A monad fragment reads `rdi`, a dyad
  fragment reads `rdi`/`rsi`, a nilad fragment reads nothing. Fragments
  preserve `rbx`, `rbp`, `r12–r15`.
- Runtime routines take args in `rdi`/`rsi`, return in `rax`, use `r11` as
  scratch, and preserve the callee-saved set (so a link's `r12`/`r13` survive).

## No backpatching

Three properties make every emitted byte position-independent, so a fragment's
bytes never change based on where they land:

1. Runtime calls are **absolute-indirect**: `movabs r11, addr; call r11`.
2. Loop/branch jumps are **intra-fragment relative** (`E9`/`0F 8D` rel32),
   and a combinator wraps an *already-emitted* operand, so the displacement is
   just that operand's known length.
3. `Ç ç ¢` call **backward-only** links (rule R4); a link's absolute address is
   `BASE + offset` and is known by the time any later link references it.

The only value written "late" is the main link's address, stored into the
runtime's `main_ptr` cell after all links are laid out — a plain computed
value, not a relocation.

## Chain lowering

The compiler parses a link's tokens into a chain of `Link` objects (atoms are
links; a quick/hyper pops preceding links and yields a combined link, exactly
like the interpreter's `parse_code`), then replays the interpreter's
`monadic_chain` rules to glue their fragments. With `ret` in `rax` and `λ` in
`r12`:

| Head pattern | Emitted |
| --- | --- |
| leading nilad | `ret ← N` (else `ret ← λ`, i.e. `mov rax,r12`) |
| `[2,1]` | `push rax; mov rdi,r12; <M>; mov rsi,rax; pop rdi; <D>` |
| `[2,0]` | `push rax; <N>; mov rsi,rax; pop rdi; <D>` |
| `[0,2]` | `push rax; <N>; mov rdi,rax; pop rsi; <D>` |
| `[2]` | `mov rdi,rax; mov rsi,r12; <D>` |
| `[1]` | `mov rdi,rax; <M>` |

Dyadic-chain lowering (for links called via `ç`/`ŀ`) adds the `[2,2,2]`,
`[2,2,0]`, and `[2,2]` heads from SPEC.md; it shares the same glue.

## The `€` map

`€` pops one monadic operand and emits an inline loop. The argument is first
range-ified (`rt_iterable(x, make_range=1)`: an int `x` becomes `1..x`, a list
passes through), then each element runs the operand fragment into a fresh
destination list. `r14` = source, `r15` = dest, `rbx` = index — all pushed on
entry and popped on exit, so nested `€` loops don't collide.

```
mov rdi,rax; mov esi,1; call rt_iterable      ; source list
push r14; push r15; push rbx
mov r14,rax; mov rdi,[r14]; call rt_alloc      ; dest
mov r15,rax; xor rbx,rbx
loop:  cmp rbx,[r14]; jge done
       mov rdi,[r14+rbx*8+8]; <operand>; mov [r15+rbx*8+8],rax; inc rbx; jmp loop
done:  mov rax,r15; pop rbx; pop r15; pop r14
```

## ELF layout

```
0x400000  Ehdr (64B, ET_EXEC, EM_X86_64, one program header, no sections)
0x400040  Phdr (56B, PT_LOAD, flags RWX, vaddr=BASE, filesz=memsz=image length)
0x400100  runtime blob (RT_BASE); entry point = _start at its first byte.
          The blob's data cells (main_ptr, bump_ptr, buffers) live at its end.
   …      compiled links, 16-byte aligned, in source order (main link last)
```

The image is assembled as one contiguous file loaded at `BASE`, so a byte's
file offset equals `vaddr − BASE`. One RWX segment (cc500-style) keeps the
emitter trivial; an R-X / RW- split is a future hardening option.

## Instruction encodings

All machine-code byte sequences in `ref/jellyc.py` (the `I_*` constants) were
verified against binutils (`as` + `objdump -d -M intel`). Near jumps use the
32-bit-displacement forms (`E9`, `0F 8D`) unconditionally so displacements are
never mis-sized.
