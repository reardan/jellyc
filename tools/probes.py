#!/usr/bin/env python3
"""Semantic probes: one executable assertion per interpreter fact that the
JellyCore design relies on. Run against the pinned vendored interpreter.

If any probe fails after an interpreter bump, JellyCore's spec (and possibly
the compiler) no longer matches stage0 semantics - fix that before shipping.

usage: probes.py            run all probes, exit nonzero on failure
       probes.py --discover print actual values for probes marked DISCOVER
"""
import sys

import jellyenv

DISCOVER = object()
failures = []
discover_mode = "--discover" in sys.argv[1:]


def probe(pid, code, args, expected, note):
    got = jellyenv.jelly_eval(code, args)
    if expected is DISCOVER:
        print(f"DISCOVER {pid}: {code!r} {args!r} -> {got!r}   ({note})")
        return
    if got != expected:
        failures.append(pid)
        print(f"FAIL {pid}: {code!r} {args!r} -> {got!r}, expected {expected!r}   ({note})")
    elif discover_mode:
        print(f"ok   {pid}: {code!r} -> {got!r}")


def m(pid, code, left, expected, note):
    """Monadic program probe: one argument, so ⁹ keeps its 256 default."""
    probe(pid, code, [left], expected, note)


def d(pid, code, left, right, expected, note):
    """Dyadic program probe: two arguments, dyadic chain rules."""
    probe(pid, code, [left, right], expected, note)


# --- literals and nilads ----------------------------------------------------
m("lit-str", "“abc‘", 0, [97, 98, 99], "“...‘ is a flat list of codepage ints")
m("lit-str-empty", "“‘", 0, [], "“‘ is the empty list")
m("lit-str-pilcrow", "“a¶b‘", 0, [97, 127, 98], "¶ legal inside “...‘, is byte 127")
m("lit-int", "42", 0, 42, "digit-run literal")
m("lit-list", "1,2,3", 0, [1, 2, 3], "comma list is one literal token")
m("nilad-100", "³", 0, 100, "³ = 100")
m("arg-left", "⁸", [5, 6], [5, 6], "⁸ = left argument")
m("arg-right-default", "⁹", [5, 6], 256, "⁹ defaults to 256 under monadic call")

# --- monadic atoms ----------------------------------------------------------
m("L-list", "L", [10, 20, 30], 3, "length")
m("L-int", "L", 5, 1, "L of an int is 1 (iterable wrap)")
m("F", "F", [[1, [2]], 3], [1, 2, 3], "deep flatten")
m("Rev", "Ṛ", [1, 2, 3], [3, 2, 1], "reverse list")
m("R", "R", 3, [1, 2, 3], "range 1..n")
m("R-zero", "R", 0, [], "range of 0 is empty")
m("Drop1", "Ḋ", [1, 2, 3], [2, 3], "drop first")
m("Init", "Ṗ", [1, 2, 3], [1, 2], "drop last")
m("no-mutate", "Ḋ;⁸", [1, 2, 3], [2, 3, 1, 2, 3], "Ḋ must not mutate its argument")
m("inc", "‘", 5, 6, "increment")
m("dec", "’", 5, 4, "decrement")
m("not0", "¬", 0, 1, "logical not of 0")
m("not3", "¬", 3, 0, "logical not of nonzero")
m("id", "¹", [7], [7], "identity")

# --- dyadic atoms -----------------------------------------------------------
d("add", "+", 3, 4, 7, "addition")
d("sub", "_", 3, 4, -1, "subtraction")
d("mul", "×", 3, 4, 12, "multiplication")
d("fdiv", ":", 7, 2, 3, "floor division")
d("fdiv-neg", ":", -7, 2, -4, "floored (not truncated) division")
d("fmod", "%", 7, 2, 1, "floor modulus")
d("fmod-neg", "%", -7, 2, 1, "floored modulus, sign of divisor")
d("eq", "=", 3, 3, 1, "int equality")
d("lt", "<", 3, 4, 1, "less than")
d("gt", ">", 3, 4, 0, "greater than")
d("ne-compose", "=¬", 3, 4, 1, "x≠y spelled =¬ (this interpreter has no ≠ atom)")
d("le-compose", ">¬", 4, 4, 1, "x≤y spelled >¬")
d("ge-compose", "<¬", 3, 4, 0, "x≥y spelled <¬")
d("deepeq", "⁼", [1, [2]], [1, [2]], 1, "deep non-vectorizing equality")
d("deepeq-ne", "⁼", [1, [2]], [1, [3]], 0, "deep equality mismatch")
d("cat-ss", ";", 1, 2, [1, 2], "concat wraps scalars")
d("cat-ls", ";", [1], 2, [1, 2], "concat list+scalar")
d("cat-sl", ";", 1, [2], [1, 2], "concat scalar+list")
d("cat-ll", ";", [1], [2], [1, 2], "concat lists")
m("pair", "L,L", [5, 6], [2, 2], ", pairs its operands")
d("tack", "ṭ", 5, [1, 2], [1, 2, 5], "ṭ appends left to right")
d("at-index", "ị", 2, [10, 20, 30], 20, "ị: left arg is 1-based index")
d("at-index-0", "ị", 0, [10, 20, 30], 30, "ị index 0 wraps to last")
d("at-index-mod", "ị", 4, [10, 20, 30], 10, "ị is modular beyond length")
d("at-index-empty", "ị", 1, [], 0, "ị on empty list gives 0")
d("index-of", "i", [10, 20], 20, 2, "i: 1-based position")
d("index-of-miss", "i", [10, 20], 99, 0, "i: 0 when absent")
d("take", "ḣ", [1, 2, 3], 2, [1, 2], "ḣ takes first y")
d("take-clamp", "ḣ", [1, 2], 5, [1, 2], "ḣ clamps like a Python slice")
d("tailfrom", "ṫ", [1, 2, 3], 2, [2, 3], "ṫ = x[y-1:]")
d("tailfrom-1", "ṫ", [1, 2, 3], 1, [1, 2, 3], "ṫ 1 is the whole list")
d("repeat", "ẋ", [1, 2], 2, [1, 2, 1, 2], "ẋ repeats a list")
d("repeat-scalar", "ẋ", 5, 2, [5, 5], "ẋ wraps a scalar first")
d("repeat-0", "ẋ", [1, 2], 0, [], "ẋ 0 is empty")
d("tobase", "b", 255, 16, [15, 15], "b: big-endian digits")
d("tobase-0", "b", 0, 16, [0], "b of 0 is [0]")
d("frombase", "ḅ", [15, 15], 16, 255, "ḅ: digits to int")

# --- quicks and hypers ------------------------------------------------------
m("each", "‘€", [3, 5], [4, 6], "€ maps a monad")
m("each-rangeify", "‘€", 3, [2, 3, 4], "€ range-ifies an int argument")
d("zip-tail", '+"', [1, 2, 3], [10, 20], [11, 22, 3], '" keeps the longer tail')
m("fold", "+/", [1, 2, 3, 4], 10, "/ left fold")
m("filter", "¬Ƈ", [0, 1, 0, 2], [0, 0], "Ƈ keeps truthy-predicate elements")
m("ternary-then", "‘’¬?", 0, 1, "? pops then,else,cond; cond ¬0 truthy")
m("ternary-else", "‘’¬?", 7, 6, "? takes else branch when cond falsy")
m("while", "’¹¿", 5, 0, "¿ pops body,cond; loops while cond truthy")
m("group2", "‘‘$", 5, 7, "$ groups two links into a monad")
m("group2-tail", "‘+$", 5, 11, "$-group: chain [‘,+] on x is (x+1)+x")
d("swap", "_@", 3, 10, 7, "@ swaps dyad arguments")
d("left-monad", "L{", [1, 2], [5, 6, 7], 2, "{ applies monad to left arg")
d("right-monad", "L}", [1, 2], [5, 6, 7], 3, "} applies monad to right arg")
m("group3", "‘‘‘Ɗ", 5, 8, "Ɗ groups three links")
m("group4", "‘‘‘‘Ʋ", 5, 9, "Ʋ groups four links")
d("group2-dyad", "+‘¥", 3, 4, 8, "¥ groups two links into a dyad")
m("args-rebound", "⁸‘$€", [3, 4], [4, 5],
  "⁸ inside a $-group is rebound per call (motivates rule R3)")

# --- chain patterns ---------------------------------------------------------
m("mchain-2-0", "+3", 5, 8, "monadic [2,0]: trailing nilad")
m("mchain-0-2", "3+", 5, 8, "monadic [0,2]: leading nilad feeds dyad")
m("mchain-2-1", "+‘", 5, 11, "monadic [2,1]: x + inc(x)")
m("mchain-2", "+", 5, 10, "monadic [2]: dyad reuses the argument")
d("dchain-2-2", "+×", 3, 4, 15, "dyadic mid [2,2]: ret = D1(ret, D2(λ,ρ))")
d("dchain-2-2-2", "+×+", 3, 4, 49, "dyadic leading [2,2,2]: ret = D1(λ,ρ), then [2,2]")
d("dchain-2-2-0", "+×3", 3, 4, 21, "dyadic [2,2,0]+nilad: ret = D2(D1(ret,ρ), N)")

# --- link references --------------------------------------------------------
m("linkref-L", "‘¶1Ŀ", 5, 6, "1Ŀ calls link 1 as a monad")
m("linkref-L2", "‘¶’¶2Ŀ", 5, 4, "2Ŀ calls link 2")
m("linkref-C", "‘¶Ç", 5, 6, "Ç calls the previous link as a monad")
m("linkref-c", "+¶3ç4", 0, 7, "ç calls the previous link as a dyad")
m("linkref-nilad", "5¶¢‘", 0, 6, "¢ calls the previous link as a nilad")
m("linkref-nilad-arg", "‘¶¢", 9, 1,
  "a niladic call evaluates the target monadically with argument 0")
m("linkref-pound", "7¶1£", 0, 7, "n£ calls link n as a nilad")
m("recursion", "’ß$0¹?", 3, 0, "ß recurses the current link")

# ----------------------------------------------------------------------------
if failures:
    print(f"\n{len(failures)} probe(s) FAILED: {', '.join(failures)}")
    sys.exit(1)
print(f"all probes passed ({'discover mode' if discover_mode else 'assert mode'})")
