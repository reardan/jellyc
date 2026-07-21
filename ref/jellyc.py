#!/usr/bin/env python3
"""jellyc reference compiler (Python).

This is the executable specification for jellyc: it implements the same
JellyCore -> x86-64 ELF pipeline that src/jellyc.d/ (the self-hosting Jelly
source) implements, but in readable Python. It doubles as:

  * the subset checker      (jellyc.py --check FILE)
  * the differential oracle (jellyc.py FILE.sbcs OUT.elf   -- M3+)

Milestone status: M1 delivers the tokenizer and the static checker (rules R1
and R4 from SPEC.md). Codegen (chain lowering + ELF emission) lands in M3;
the parser scaffold it needs is already shaped here.

Tokenization mirrors the reference interpreter's grammar so JellyCore source
tokenizes identically under both. See SPEC.md for the frozen token set.
"""
import os
import re
import sys

# --- token classification (SPEC.md Tokens) ---------------------------------

# arity-1 atoms
MONADS = set("LFṚRḊṖW‘’¬¹")
# arity-2 atoms
DYADS = set("+_×:%=<>⁼;,ṭịiḣṫẋbḅ")
# nilad glyphs (literals are handled separately)
NILADS = set("⁸⁹³⁴⁵")
# combinators that pop exactly one preceding link (interpreter "hypers")
HYPERS = set('€"@{}')
# link-reference hypers that pop one preceding literal index
LINKREF_HYPERS = set("Ŀŀ£")
# combinators that pop by arity condition (interpreter "quicks")
QUICKS = set("?¿/$¥ƊƲƇ")
# link references that pop nothing
LINKREF_QUICKS = set("ßÇç¢")

# glyphs explicitly banned by R1 even though the interpreter understands them
BANNED = {
    "≠": "use =¬", "≤": "use >¬", "≥": "use <¬",
    "Ḣ": "mutating; use 1ị or Ḋ", "Ṫ": "mutating; use ṫ or Ṗ",
    "Ñ": "forward link ref (R4)", "ñ": "forward link ref (R4)",
    "µ": "chain separator", "ø": "chain separator",
    "ð": "chain separator", "ɓ": "chain separator",
    ")": "chain separator", "¤": "nilad chain",
    "”": "char literal (str)", "⁶": "space char", "⁷": "newline char",
}

# Literal token shapes. A JellyCore string is “...‘ with no forbidden bytes
# (250..255 = « » ‘ ’ ” “) inside. A number literal is a non-negative digit
# run; a comma list chains them.
STR_LIT = "“[^«»‘’”“]*‘"
NUM_LIT = r"\d+(?:,\d+)*"
REGEX_LITERAL = re.compile("(?:%s|%s)" % (STR_LIT, NUM_LIT))

ALL_SINGLE = MONADS | DYADS | NILADS | HYPERS | LINKREF_HYPERS | QUICKS | LINKREF_QUICKS


class Token:
    __slots__ = ("kind", "glyph", "value")

    def __init__(self, kind, glyph, value=None):
        self.kind = kind        # 'lit' | 'monad' | 'dyad' | 'nilad' |
        self.glyph = glyph      # 'hyper' | 'linkhyper' | 'quick' | 'linkquick'
        self.value = value      # python value for literals

    def __repr__(self):
        if self.kind == "lit":
            return f"Token(lit {self.value!r})"
        return f"Token({self.kind} {self.glyph!r})"


class JellyCoreError(Exception):
    def __init__(self, link_index, message):
        super().__init__(f"link {link_index + 1}: {message}")
        self.link_index = link_index
        self.message = message


def _parse_literal(text):
    """Turn a matched literal token into its JellyCore value (int or list)."""
    if text.startswith("“"):
        body = text[1:-1]  # strip “ and ‘
        return [ord_cp(ch) for ch in body]
    parts = text.split(",")
    nums = [int(p) for p in parts]
    return nums[0] if len(nums) == 1 else nums


# codepage helpers, imported lazily so the tokenizer works without the vendor
_CODE_PAGE = None


def _code_page():
    global _CODE_PAGE
    if _CODE_PAGE is None:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        os.pardir, "tools"))
        import jellyenv
        _CODE_PAGE = jellyenv.code_page
    return _CODE_PAGE


def ord_cp(ch):
    return _code_page().index(ch)


def tokenize_link(text, link_index):
    """Tokenize one link (no ¶). Returns a list of Token. Raises on R1
    violations (unknown glyph, banned glyph, malformed literal)."""
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == " ":
            i += 1
            continue
        m = REGEX_LITERAL.match(text, i)
        if m and m.start() == i:
            tokens.append(Token("lit", None, _parse_literal(m.group())))
            i = m.end()
            continue
        if ch in BANNED:
            raise JellyCoreError(link_index, f"banned token {ch!r} ({BANNED[ch]}) [R1]")
        if ch in MONADS:
            tokens.append(Token("monad", ch))
        elif ch in DYADS:
            tokens.append(Token("dyad", ch))
        elif ch in NILADS:
            tokens.append(Token("nilad", ch))
        elif ch in HYPERS:
            tokens.append(Token("op", ch, "hyper"))
        elif ch in LINKREF_HYPERS:
            tokens.append(Token("op", ch, "linkhyper"))
        elif ch in QUICKS:
            tokens.append(Token("op", ch, "quick"))
        elif ch in LINKREF_QUICKS:
            tokens.append(Token("op", ch, "linkquick"))
        elif ch == "“":
            raise JellyCoreError(link_index, "unterminated “...‘ string [R1]")
        else:
            raise JellyCoreError(link_index, f"unknown token {ch!r} [R1]")
        i += 1
    return tokens


def split_links(text):
    """Split source into links. The reference interpreter's internal string
    form separates links with the pilcrow '¶' (code page byte 0x7f); we also
    accept a literal newline so UTF-8 .jelly files are one link per line."""
    return re.split("[¶\x7f\n]", text)


def tokenize(text):
    """Whole-program tokenize -> list of (link tokens)."""
    return [tokenize_link(link, idx) for idx, link in enumerate(split_links(text))]


# --- static checks (SPEC.md restrictions) ----------------------------------

def check_linkrefs(links):
    """R4: Ŀ ŀ £ take a literal index that is backward and in range."""
    n = len(links)
    errors = []
    for idx, tokens in enumerate(links):
        for pos, tok in enumerate(tokens):
            if tok.kind == "op" and tok.value == "linkhyper":
                prev = tokens[pos - 1] if pos > 0 else None
                if prev is None or prev.kind != "lit" or not isinstance(prev.value, int):
                    errors.append(JellyCoreError(idx,
                        f"{tok.glyph} needs a literal integer link index before it [R4]"))
                    continue
                target = prev.value
                if not (1 <= target <= n):
                    errors.append(JellyCoreError(idx,
                        f"{tok.glyph} index {target} out of range 1..{n} [R4]"))
                elif target - 1 >= idx:
                    errors.append(JellyCoreError(idx,
                        f"{tok.glyph} index {target} is not a backward reference [R4]"))
    return errors


def check(text):
    """Run all currently-implemented static checks. Returns a list of errors
    (empty = source is within the checkable subset). R1 is enforced during
    tokenization; R2/R3/R5 arrive with the M3 parser."""
    errors = []
    try:
        links = tokenize(text)
    except JellyCoreError as e:
        return [e]
    errors.extend(check_linkrefs(links))
    return errors


# --- CLI -------------------------------------------------------------------

def _read_source(path):
    raw = open(path, "rb").read()
    if path.endswith(".jelly"):
        text = raw.decode("utf-8")
        return text[:-1] if text.endswith("\n") else text
    # .sbcs: codepage bytes
    cp = _code_page()
    return "".join(cp[b] for b in raw)


def main(argv):
    if len(argv) >= 2 and argv[1] == "--check":
        if len(argv) != 3:
            sys.exit("usage: jellyc.py --check FILE")
        errors = check(_read_source(argv[2]))
        for e in errors:
            print(e, file=sys.stderr)
        if errors:
            sys.exit(f"{len(errors)} subset violation(s)")
        print("ok: within JellyCore subset (R1, R4)")
        return
    sys.exit("codegen not implemented yet (M3); only --check is available")


if __name__ == "__main__":
    main(sys.argv)
