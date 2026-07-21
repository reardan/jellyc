# JellyCore — the subset jellyc compiles (and is written in)

jellyc is a self-hosting compiler in the spirit of
[cc500](https://homepage.ntlworld.com/edmund.grimley-evans/cc500.html): it does
not compile all of [Jelly](https://github.com/DennisMitchell/jellylanguage), it
compiles **JellyCore**, and the compiler is itself written strictly inside
JellyCore. The load-bearing property is the *semantic intersection*: every
construct JellyCore allows behaves **identically** under the reference Python
interpreter (stage0) and under jellyc's own compiled output. Self-hosting is
proven by the bootstrap fixpoint `stage2 == stage3` (byte-identical).

This file is the frozen contract. All facts below are pinned by executable
probes in `tools/probes.py`, run against the interpreter commit recorded in
`tools/vendor.sh`. An interpreter bump that changes any probe changes this
spec.

Notation: **arity** 0 = nilad, 1 = monad, 2 = dyad. "int" means a JellyCore
integer (a 63-bit signed value, see §Values). "list" means a heap list.

---

## Values

- **Integers**: signed, represented as 63-bit tagged words (see
  `docs/codegen.md`). The compiler source must never rely on values outside
  ±2⁶². Full Jelly has arbitrary-precision integers; JellyCore does not. This
  is a deliberate deviation — the compiler's own arithmetic (byte packing,
  address computation) stays far below 2⁶².
- **Lists**: heap-allocated, possibly nested, holding ints and lists. Built by
  bump allocation, never freed (like cc500).
- **No** floats, rationals, complex numbers, or the interpreter's `str`-typed
  characters. Characters are plain ints (codepage byte values).
- **Booleans** produced by comparisons are the ints `0` / `1`.

**Truthiness** (used by `?`, `¿`, `Ƈ`): an int is truthy iff non-zero; a list
is truthy iff non-empty.

---

## Tokens

Only the tokens below are legal (rule **R1**). Tokenization follows the
interpreter's own grammar (`tools/jellyenv`/`ref/jellyc.py` reuse the same
literal shapes), so JellyCore source tokenizes identically in both worlds.

### Literals and nilads (arity 0)

| Token | Value | Notes |
| --- | --- | --- |
| digit run, e.g. `42` | that non-negative int | no `-`, `.`, `ı`, `ȷ` forms |
| comma list, e.g. `1,2,3` | flat list of those ints | one literal token in Jelly's grammar |
| `“...‘` | list of codepage byte values (ints) | the only string form; `¶` (127) is legal inside; bytes 250–255 (`« » ‘ ’ ” “`) are forbidden inside |
| `“‘` | `[]` | empty list |
| `⁸` | left argument of the current link | see R3 |
| `⁹` | right argument of the current link | main link is called with `⁹ = 256`; see R3 |
| `³` | `100` | |
| `⁴` | `16` | |
| `⁵` | `10` | |

Excluded on purpose: `”c` char literals and `“...”` (interpreter yields Python
`str` — type mismatch), `⁶`/`⁷` (space/newline **as chars**), base-250 `’…’`,
`»` compression, negative / float / complex literals.

### Monadic atoms (arity 1)

| Glyph | Meaning | JellyCore domain |
| --- | --- | --- |
| `L` | length | list |
| `F` | flatten (deep) | any |
| `Ṛ` | reverse | list |
| `R` | range `1..n` (`n≤0` → `[]`) | int |
| `Ḋ` | drop first (non-mutating) | list |
| `Ṗ` | drop last | list |
| `W` | wrap: `x → [x]` | any |
| `‘` | increment | int |
| `’` | decrement | int |
| `¬` | logical not (1 if falsy else 0) | int (or list, by truthiness) |
| `¹` | identity (compiles to nothing) | any |

`Ḣ`/`Ṫ` (head/tail) are **excluded**: `Ḣ` mutates its argument in the
interpreter (`pop(0)`), which the compiled version cannot replicate. Use
`1ị` / `Ḋ` etc.

### Dyadic atoms (arity 2)

| Glyph | Meaning | Domain |
| --- | --- | --- |
| `+` `_` `×` | add, subtract, multiply | int × int |
| `:` | floor division | int × int, divisor ≠ 0 |
| `%` | floor modulus (sign of divisor) | int × int, divisor ≠ 0 |
| `=` `<` `>` | equal / less / greater → 0/1 | int × int |
| `⁼` | deep equality → 0/1 | any |
| `;` | concatenate (scalars auto-wrap) | any |
| `,` | pair → `[x, y]` | any |
| `ṭ` | tack: `iterable(y) + [x]` | right = list |
| `ị` | at-index (1-based, **modular**, index 0 = last, empty list → 0); left = index | int index |
| `i` | first index of (1-based, 0 if absent) | any |
| `ḣ` | take first `y` (Python-slice clamped) | list × int |
| `ṫ` | `x[y-1:]` (drop first `y-1`) | list × int, `y ≥ 1` |
| `ẋ` | repeat list `y` times (scalar wraps) | any × int `≥ 0` |
| `b` | to base (big-endian digit list) | int `≥ 0` × base `≥ 2` |
| `ḅ` | from base | digit list × base |

**Composed comparisons** (this interpreter has **no** `≠`/`≤`/`≥` atoms):
`x≠y` = `=¬`, `x≤y` = `>¬`, `x≥y` = `<¬`. jellyc treats these as the canonical
spellings; the checker forbids `≠ ≤ ≥`.

### Quicks and hypers (combinators)

| Glyph | Pops | Result | Lowering (see `docs/codegen.md`) |
| --- | --- | --- | --- |
| `€` | 1 | map (arity `max(1, k)`) | inline loop; int arg is range-ified (`1..x`) exactly as the interpreter |
| `"` | 1 dyad | zip | loop over `min` length, then append the longer list's tail verbatim |
| `/` | 1 dyad | left fold (monad) | inline fold; singleton → the element (dyad not called); empty list traps |
| `Ƈ` | 1 monad | filter (monad) | inline loop + truthiness + length fixup |
| `?` | 3 | max arity | `then,else,cond` in source order; branch on truthiness of `cond` |
| `¿` | 2 | max arity | `body,cond`; while `cond` truthy, `x ← body(x)`; monadic use only |
| `$` | 2 | monad group | recursively chain-compile the two popped links at arity 1 |
| `¥` | 2 | dyad group | same, arity 2 |
| `Ɗ` | 3 | monad group | arity 1 |
| `Ʋ` | 4 | monad group | arity 1 |
| `@` | 1 dyad | dyad, args swapped | prefix `xchg rdi, rsi` |
| `{` | 1 monad | dyad applying monad to **left** arg | drop right |
| `}` | 1 monad | dyad applying monad to **right** arg | `rdi ← rsi` |

Quicks/hypers pop **already-parsed** links, so the whole parser is a single
left-to-right pass with an explicit fragment stack — no recursion, no
lookahead. `$ ¥ Ɗ Ʋ` are the only nesting constructs and they just re-invoke
the chain compiler on their operands.

### Link references

| Glyph | Meaning | Restriction |
| --- | --- | --- |
| `Ç` / `ç` / `¢` | call the previous link (index−1) as monad / dyad / nilad | — |
| `<n>Ŀ` / `<n>ŀ` / `<n>£` | call link `n` (1-based over `links[:-1]`) as monad / dyad / nilad | `n` a literal; **backward only** (R4) |
| `ß` | recurse the current link at the current arity | — |

A **niladic** call (`¢`, `n£`) evaluates the target as a monadic chain with
argument `0` (matching the interpreter's `niladic_chain → monadic_chain(chain,
0)`). The interpreter's `Ŀ`/`ŀ` indices are modular over `links[:-1]`; JellyCore
requires the literal index to already be in `1..len-1` and backward, so the
modulus never triggers.

---

## Chain evaluation

JellyCore evaluates a link's chain by the interpreter's exact rules
(`monadic_chain` / `dyadic_chain`), which jellyc replays **at compile time** to
lower a chain into a straight-line instruction sequence. `arities(c)` is the
arity list; a **leading nilad** is a chain whose `arities + [1] < [0,2]*len`
(interpreter's `leading_nilad`) — informally, it starts with a nilad not
immediately consumed as the right operand of a dyad.

**Monadic chain** over argument `λ` (`ret` starts at `λ`, or the leading nilad):

| Head pattern | Effect |
| --- | --- |
| `[2,1]` | `ret ← D(ret, M(λ))` |
| `[2,0]` | `ret ← D(ret, N)` |
| `[0,2]` | `ret ← D(N, ret)` |
| `[2]` | `ret ← D(ret, λ)` |
| `[1]` | `ret ← M(ret)` |

**Dyadic chain** over `(λ, ρ)` (`ret` starts at `λ`; if the chain opens `[2,2,2]`
then `ret ← D₀(λ, ρ)` first; else if it opens with a leading nilad, `ret ← N`):

| Head pattern | Effect |
| --- | --- |
| `[2,2,0]` + trailing leading-nilad | `ret ← D₂(D₁(ret, ρ), N)` |
| `[2,2]` | `ret ← D₁(ret, D₂(λ, ρ))` |
| `[2,0]` | `ret ← D(ret, N)` |
| `[0,2]` | `ret ← D(N, ret)` |
| `[2]` | `ret ← D(ret, ρ)` |
| `[1]` | `ret ← M(ret)` |

A mid-chain unconsumed nilad triggers the interpreter's implicit
`output(ret)`; JellyCore **forbids** that position (rule R2) so nothing prints
mid-chain.

---

## I/O convention

A compiled program is a filter:

- **stdin** (all of it) → the main link's **left** argument, as a list of byte
  values (ints `0..255`).
- The main link's **right** argument `⁹` defaults to `256` (matching the
  interpreter default under a one-argument call).
- The main link's **result** is deep-flattened to a list of ints, each written
  to **stdout** as one raw byte (must be `0..255`). Exit code 0.

This replaces Jelly's argv input and codepage "smash" output. `bootstrap/stage0.py`
mirrors it exactly so the interpreter and compiled binaries agree byte-for-byte.

---

## Restrictions (the "written in the intersection" contract)

Statically enforced by `ref/jellyc.py --check` where marked *(static)*;
otherwise enforced by differential tests + runtime traps.

- **R1** *(static)*: only the tokens in §Tokens. No chain separators
  (`µ ø ð ɓ ) ¤`), no `Ñ ñ`, no atoms/quicks/hypers outside this file, no
  mutating atoms (`Ḣ Ṫ`), no `≠ ≤ ≥`.
- **R2** *(static)*: a nilad may appear only in a position the chain rules
  consume (leading, `[2,0]`, `[0,2]`, `[2,2,0]`-trailing). A nilad that would
  hit the interpreter's mid-chain `output(ret)` is a compile error.
- **R3** *(static)*: `⁸`/`⁹` may not appear inside a modifier operand
  (`€ " / Ƈ ? ¿ $ ¥ Ɗ Ʋ @ { }` bodies) **nor** inside a link reached by a
  niladic call (`¢ n£`). At link top level they mean the link's own arguments in
  both worlds; inside groups/niladic calls the interpreter's dynamic rebinding
  and jellyc's saved-register model can disagree.
- **R4** *(static)*: `Ŀ ŀ £` indices are literal nilads with
  `1 ≤ n < current_link_index` (backward only). Self-recursion uses `ß`; mutual
  recursion is never needed (the parser is a linear stack algorithm).
- **R5** *(static)*: every non-main link is called at exactly one arity;
  the main link is monadic. A link compiled once, at that arity.
- **R6** *(dynamic)*: atoms are applied only within their §Tokens domains
  (int-only arithmetic/compares, list args to list ops, non-zero divisors,
  non-empty `/`). Violations trap (`rt_abort`) in compiled code and
  raise/misbehave under the interpreter; the differential suite keeps the
  compiler source inside the shared domain.

---

## Deviations from full Jelly (summary)

1. No depth-based auto-vectorization — iteration is always explicit (`€ " /`).
2. 63-bit wrapping integers, not bignums.
3. No floats / rationals / complex / `str` characters — chars are ints.
4. Bytes-in / bytes-out I/O instead of argv + codepage smash-output.
5. Comparison atoms `≠ ≤ ≥` are spelled `=¬ >¬ <¬`.
6. GIGO: an unknown token *in a program jellyc compiles* lowers to an
   `rt_abort` call site rather than a diagnostic.
