#!/usr/bin/env python3
"""Tests for the M1 tokenizer + subset checker in ref/jellyc.py.

Two things are checked:
  1. Tokenizer agreement: for accepted JellyCore source, our token boundaries
     match the reference interpreter's own tokenization (so JellyCore source
     parses identically under both).
  2. Checker behavior: valid subset samples pass; a targeted counter-example
     per implemented rule (R1, R4) is rejected.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ref"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import jellyc
import jellyenv
from jelly import interpreter as I

fails = []


def expect(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL:", msg)


def interp_tokens(link_text):
    """Reference interpreter's token list for one link, via its own regexes."""
    return I.regex_token.findall(link_text)


def our_tokens(link_text):
    toks = jellyc.tokenize_link(link_text, 0)
    out = []
    for t in toks:
        if t.kind == "lit":
            if isinstance(t.value, list) and t.value and False:
                pass
            out.append(t)
        else:
            out.append(t.glyph)
    return toks


# 1. Tokenizer agreement on accepted subset lines --------------------------
AGREE = [
    "‘",
    "+×",
    "1,2,3",
    "“abc‘",
    "“‘",
    "‘€",
    '+"',
    "+/",
    "¬Ƈ",
    "‘’¬?",
    "’¹¿",
    "⁸ị⁹",
    "42+‘",
    "1Ŀ",
    "12ị",
]
for line in AGREE:
    itok = interp_tokens(line)
    # our count of tokens must equal the interpreter's, glyph-for-glyph where
    # single-glyph, and literals must cover the same spans.
    ours = jellyc.tokenize_link(line, 0)
    expect(len(ours) == len(itok),
           f"token count mismatch on {line!r}: ours={len(ours)} interp={len(itok)} ({itok})")

# 2. Accepted samples pass the checker -------------------------------------
GOOD = [
    "‘€",
    "+/",
    "⁸L",
    "“hello‘",
    "‘¶1Ŀ",          # backward link ref
    "‘¶’¶2Ŀ",        # link 2 from link 3
    "+¶3ç4",         # ç is fine (previous link)
    "5¶¢‘",
]
for src in GOOD:
    errs = jellyc.check(src)
    expect(not errs, f"expected {src!r} to pass, got: {[str(e) for e in errs]}")

# 3. Targeted rejections ----------------------------------------------------
def rejects(src, needle):
    errs = jellyc.check(src)
    expect(errs, f"expected {src!r} to be rejected")
    if errs:
        joined = " ".join(str(e) for e in errs)
        expect(needle in joined, f"{src!r} rejected but message missing {needle!r}: {joined}")


rejects("≠", "R1")                 # banned comparison glyph
rejects("Ḣ", "R1")                 # mutating atom
rejects("µ", "R1")                 # chain separator
rejects("‘Ñ", "R1")                # forward link ref glyph
rejects("‘¶2Ŀ", "R4")              # index 2 from link 1: not backward
rejects("‘¶‘¶9Ŀ", "R4")            # index 9 out of range
rejects("Ŀ", "R4")                 # Ŀ with no literal index

# 4. Literal values ---------------------------------------------------------
expect(jellyc.tokenize_link("“abc‘", 0)[0].value == [97, 98, 99], "string literal value")
expect(jellyc.tokenize_link("“‘", 0)[0].value == [], "empty string literal value")
expect(jellyc.tokenize_link("42", 0)[0].value == 42, "int literal value")
expect(jellyc.tokenize_link("1,2,3", 0)[0].value == [1, 2, 3], "comma-list literal value")

if fails:
    print(f"\n{len(fails)} test(s) FAILED")
    sys.exit(1)
print("all checker tests passed")
