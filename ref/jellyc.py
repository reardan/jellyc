#!/usr/bin/env python3
"""jellyc reference compiler (Python).

This is the executable specification for jellyc: it implements the same
JellyCore -> x86-64 ELF pipeline that src/jellyc.d/ (the self-hosting Jelly
source) implements, but in readable Python. It doubles as:

  * the subset checker      (jellyc.py --check FILE)
  * the differential oracle (jellyc.py FILE.sbcs OUT.elf   -- M3+)

Milestone status: M1 delivers the tokenizer and static checker (rules R1/R4).
M3 (in progress) adds x86-64 codegen and ELF emission for a growing slice of
the subset - see CODEGEN below. Tokenization mirrors the reference
interpreter's grammar so JellyCore source tokenizes identically under both.
See SPEC.md for the frozen token set and docs/codegen.md for the lowering.
"""
import os
import re
import struct
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


# ===========================================================================
# CODEGEN (M3)
#
# Value tagging matches src/runtime/runtime.s: int v -> (v<<1)|1, list -> ptr.
# A compiled *link* is a function:  push r12;push r13; r12=rdi; r13=rsi;
# <body leaves rax>; pop r13;pop r12; ret.  r12/r13 hold the link's own
# arguments (left/right). A *fragment* leaves its result in rax; monad
# fragments read rdi, dyad fragments read rdi/rsi, nilad fragments read
# nothing. The chain compiler glues fragments per SPEC.md's chain rules.
#
# All runtime calls are absolute-indirect (movabs r11,addr; call r11) and all
# jumps are intra-fragment relative, so fragment bytes are position-
# independent - no backpatching. Cross-link calls (Ç) are backward-only, so
# the target address is already known when the call is emitted.
# ===========================================================================

BASE = 0x400000
RT_BASE = 0x400100

# verified instruction encodings (see tools/ probing against binutils)
I_PUSH_R12 = bytes([0x41, 0x54])
I_PUSH_R13 = bytes([0x41, 0x55])
I_POP_R13 = bytes([0x41, 0x5D])
I_POP_R12 = bytes([0x41, 0x5C])
I_PUSH_RAX = bytes([0x50])
I_POP_RDI = bytes([0x5F])
I_POP_RSI = bytes([0x5E])
I_PUSH_R14 = bytes([0x41, 0x56])
I_PUSH_R15 = bytes([0x41, 0x57])
I_POP_R15 = bytes([0x41, 0x5F])
I_POP_R14 = bytes([0x41, 0x5E])
I_PUSH_RBX = bytes([0x53])
I_POP_RBX = bytes([0x5B])
I_MOV_R12_RDI = bytes([0x49, 0x89, 0xFC])
I_MOV_R13_RSI = bytes([0x49, 0x89, 0xF5])
I_MOV_RAX_R12 = bytes([0x4C, 0x89, 0xE0])
I_MOV_RAX_R13 = bytes([0x4C, 0x89, 0xE8])
I_MOV_RDI_R12 = bytes([0x4C, 0x89, 0xE7])
I_MOV_RSI_R12 = bytes([0x4C, 0x89, 0xE6])
I_MOV_RSI_R13 = bytes([0x4C, 0x89, 0xEE])
I_MOV_RDI_RAX = bytes([0x48, 0x89, 0xC7])
I_MOV_RSI_RAX = bytes([0x48, 0x89, 0xC6])
I_MOV_RAX_RDI = bytes([0x48, 0x89, 0xF8])
I_MOV_R14_RAX = bytes([0x49, 0x89, 0xC6])
I_MOV_R15_RAX = bytes([0x49, 0x89, 0xC7])
I_MOV_RAX_R15 = bytes([0x4C, 0x89, 0xF8])
I_MOV_RDI_MEM_R14 = bytes([0x49, 0x8B, 0x3E])           # mov rdi,[r14]
I_MOV_RDI_R14RBX = bytes([0x49, 0x8B, 0x7C, 0xDE, 0x08])  # mov rdi,[r14+rbx*8+8]
I_MOV_R15RBX_RAX = bytes([0x49, 0x89, 0x44, 0xDF, 0x08])  # mov [r15+rbx*8+8],rax
I_CMP_RBX_MEM_R14 = bytes([0x49, 0x3B, 0x1E])            # cmp rbx,[r14]
I_XOR_RBX_RBX = bytes([0x48, 0x31, 0xDB])
I_INC_RBX = bytes([0x48, 0xFF, 0xC3])
I_MOV_ESI_1 = bytes([0xBE, 0x01, 0x00, 0x00, 0x00])
I_ADD_RAX_RSI = bytes([0x48, 0x01, 0xF0])
I_DEC_RAX = bytes([0x48, 0xFF, 0xC8])
I_ADD_RAX_2 = bytes([0x48, 0x83, 0xC0, 0x02])
I_SUB_RAX_2 = bytes([0x48, 0x83, 0xE8, 0x02])
I_RET = bytes([0xC3])
I_CALL_R11 = bytes([0x41, 0xFF, 0xD3])


def tag_int(v):
    return ((v << 1) | 1) & 0xFFFFFFFFFFFFFFFF


def movabs_rax(imm):
    return bytes([0x48, 0xB8]) + struct.pack("<Q", imm & 0xFFFFFFFFFFFFFFFF)


def movabs_r11(imm):
    return bytes([0x49, 0xBB]) + struct.pack("<Q", imm & 0xFFFFFFFFFFFFFFFF)


def call_abs(addr):
    return movabs_r11(addr) + I_CALL_R11


def jmp_rel32(rel):
    return bytes([0xE9]) + struct.pack("<i", rel)


def jge_rel32(rel):
    return bytes([0x0F, 0x8D]) + struct.pack("<i", rel)


class Backend:
    """Holds the runtime blob + symbol addresses and lays out the ELF."""

    def __init__(self):
        build = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             os.pardir, "build")
        self.blob = open(os.path.join(build, "blob.bin"), "rb").read()
        self.sym = {}
        for line in open(os.path.join(build, "blob.syms")):
            name, off = line.split()
            self.sym[name] = RT_BASE + int(off)

    def rt(self, name):
        return self.sym[name]


# --- a Link is a fragment producer with a known arity ----------------------

class Link:
    """A parsed link: knows its arity and can emit a fragment for the arity
    at which the chain rules invoke it. `ctx` carries the backend and the
    absolute addresses of already-placed links (for Ç)."""

    arity = 1

    def mono(self, ctx):
        raise JellyCoreError(0, "link is not usable as a monad")

    def dyad(self, ctx):
        raise JellyCoreError(0, "link is not usable as a dyad")

    def nilad(self, ctx):
        raise JellyCoreError(0, "link is not usable as a nilad")


class AtomLink(Link):
    def __init__(self, glyph, arity, emitter):
        self.glyph = glyph
        self.arity = arity
        self._emit = emitter

    def mono(self, ctx):
        return self._emit(ctx)

    def dyad(self, ctx):
        return self._emit(ctx)


class NiladLink(Link):
    arity = 0

    def __init__(self, emitter):
        self._emit = emitter

    def nilad(self, ctx):
        return self._emit(ctx)


class EachLink(Link):
    """€: map the operand monad over an iterable argument (int -> range)."""

    arity = 1

    def __init__(self, operand):
        self.operand = operand

    def mono(self, ctx):
        body = self.operand.mono(ctx)
        pre = (
            I_MOV_RDI_RAX + I_MOV_ESI_1 + call_abs(ctx.rt("rt_iterable"))
            + I_PUSH_R14 + I_PUSH_R15 + I_PUSH_RBX
            + I_MOV_R14_RAX + I_MOV_RDI_MEM_R14 + call_abs(ctx.rt("rt_alloc"))
            + I_MOV_R15_RAX + I_XOR_RBX_RBX
        )
        # loop head: cmp rbx,[r14]; jge done
        cmp = I_CMP_RBX_MEM_R14
        # body between jge and jmp:
        loop_body = (
            I_MOV_RDI_R14RBX + body + I_MOV_R15RBX_RAX + I_INC_RBX
        )
        # jge skips loop_body + jmp(5); jmp goes back to cmp
        jge = jge_rel32(len(loop_body) + 5)
        back = -(len(cmp) + len(jge) + len(loop_body) + 5)
        jmp = jmp_rel32(back)
        post = I_MOV_RAX_R15 + I_POP_RBX + I_POP_R15 + I_POP_R14
        return pre + cmp + jge + loop_body + jmp + post


class PrevLink(Link):
    """Ç/ç/¢: call the immediately preceding link (by index) at a fixed arity."""

    def __init__(self, arity, target_index):
        self.arity = arity
        self.target_index = target_index

    def _call(self, ctx):
        addr = ctx.link_addr(self.target_index)
        return call_abs(addr)

    def mono(self, ctx):
        return self._call(ctx)

    def dyad(self, ctx):
        return self._call(ctx)

    def nilad(self, ctx):
        # niladic call: evaluate target monadically with argument tagged-0
        return movabs_rax(tag_int(0)) + I_MOV_RDI_RAX + self._call(ctx)


# monad/dyad atom emitters (fragment: args in rdi[/rsi], result rax) ---------

def _rt_mono(name):
    return lambda ctx: call_abs(ctx.rt(name))


def _rt_dyad(name):
    return lambda ctx: call_abs(ctx.rt(name))


MONO_ATOMS = {
    "L": _rt_mono("rt_len"),
    "Ṛ": _rt_mono("rt_reverse"),
    "‘": lambda ctx: I_MOV_RAX_RDI + I_ADD_RAX_2,
    "’": lambda ctx: I_MOV_RAX_RDI + I_SUB_RAX_2,
    "¹": lambda ctx: I_MOV_RAX_RDI,
}

DYAD_ATOMS = {
    ";": _rt_dyad("rt_concat"),
    "+": lambda ctx: I_MOV_RAX_RDI + I_ADD_RAX_RSI + I_DEC_RAX,
}


class CodegenContext:
    def __init__(self, backend, link_addrs):
        self.backend = backend
        self._addrs = link_addrs   # absolute addr per already-placed link idx

    def rt(self, name):
        return self.backend.rt(name)

    def link_addr(self, index):
        return self._addrs[index]


class Unsupported(Exception):
    pass


def build_links(tokens, link_index, self_index):
    """Turn one link's token list into a chain of Link objects, applying
    quicks/hypers (which pop preceding links) exactly like the interpreter's
    parse_code. Returns the chain (list of Link). Raises Unsupported for
    constructs codegen does not handle yet."""
    chain = []
    for pos, tok in enumerate(tokens):
        if tok.kind == "lit":
            val = tok.value
            chain.append(NiladLink(lambda ctx, v=val: _emit_literal(ctx, v)))
        elif tok.kind == "nilad":
            if tok.glyph == "⁸":
                chain.append(NiladLink(lambda ctx: I_MOV_RAX_R12))
            elif tok.glyph == "⁹":
                chain.append(NiladLink(lambda ctx: I_MOV_RAX_R13))
            elif tok.glyph in ("³", "⁴", "⁵"):
                const = {"³": 100, "⁴": 16, "⁵": 10}[tok.glyph]
                chain.append(NiladLink(lambda ctx, c=const: movabs_rax(tag_int(c))))
            else:
                raise Unsupported(f"nilad {tok.glyph}")
        elif tok.kind == "monad":
            if tok.glyph not in MONO_ATOMS:
                raise Unsupported(f"monad {tok.glyph}")
            chain.append(AtomLink(tok.glyph, 1, MONO_ATOMS[tok.glyph]))
        elif tok.kind == "dyad":
            if tok.glyph not in DYAD_ATOMS:
                raise Unsupported(f"dyad {tok.glyph}")
            chain.append(AtomLink(tok.glyph, 2, DYAD_ATOMS[tok.glyph]))
        elif tok.kind == "op":
            if tok.glyph == "€":
                if not chain:
                    raise Unsupported("€ with no operand")
                operand = chain.pop()
                chain.append(EachLink(operand))
            elif tok.glyph in ("Ç", "ç", "¢"):
                ar = {"Ç": 1, "ç": 2, "¢": 0}[tok.glyph]
                chain.append(PrevLink(ar, self_index - 1))
            else:
                raise Unsupported(f"combinator {tok.glyph}")
        else:
            raise Unsupported(tok.kind)
    return chain


def _emit_literal(ctx, val):
    if isinstance(val, int):
        return movabs_rax(tag_int(val))
    # list literal (JellyCore literals hold ints only): alloc then store each
    # element via  mov r11, tag(e); mov [rax + 8 + 8i], r11.
    body = movabs_rax(tag_int(len(val))) + I_MOV_RDI_RAX + call_abs(ctx.rt("rt_alloc"))
    for i, e in enumerate(val):
        body += movabs_r11(tag_int(e)) + _mov_mem_rax_disp_r11(8 + 8 * i)
    return body


def _mov_mem_rax_disp_r11(disp):
    # mov [rax + disp], r11   -> REX.WR 89 modrm disp
    # 4C 89 98 <disp32>  (mod10, reg=r11(011->with REX.R), rm=rax)
    return bytes([0x4C, 0x89, 0x98]) + struct.pack("<i", disp)


def compile_monadic_chain(chain, ctx):
    """Lower a monadic chain to a body that computes rax from r12 (=λ)."""
    body = bytearray()
    c = list(chain)
    if _leading_nilad(c):
        body += c[0].nilad(ctx)
        c = c[1:]
    else:
        body += I_MOV_RAX_R12
    while c:
        ars = [l.arity for l in c[:2]]
        if ars == [2, 1]:
            body += (I_PUSH_RAX + I_MOV_RDI_R12 + c[1].mono(ctx)
                     + I_MOV_RSI_RAX + I_POP_RDI + c[0].dyad(ctx))
            c = c[2:]
        elif ars == [2, 0]:
            body += (I_PUSH_RAX + c[1].nilad(ctx) + I_MOV_RSI_RAX
                     + I_POP_RDI + c[0].dyad(ctx))
            c = c[2:]
        elif ars == [0, 2]:
            body += (I_PUSH_RAX + c[0].nilad(ctx) + I_MOV_RDI_RAX
                     + I_POP_RSI + c[1].dyad(ctx))
            c = c[2:]
        elif c[0].arity == 2:
            body += I_MOV_RDI_RAX + I_MOV_RSI_R12 + c[0].dyad(ctx)
            c = c[1:]
        elif c[0].arity == 1:
            body += I_MOV_RDI_RAX + c[0].mono(ctx)
            c = c[1:]
        else:
            raise Unsupported("mid-chain nilad (R2)")
    return bytes(body)


def _leading_nilad(chain):
    # interpreter: leading_nilad = arities + [1] < [0,2]*len (lexicographic)
    ars = [l.arity for l in chain] + [1]
    ref = [0, 2] * len(chain)
    return bool(chain) and ars < ref


def compile_link_body(chain, ctx):
    body = compile_monadic_chain(chain, ctx)
    return I_PUSH_R12 + I_PUSH_R13 + I_MOV_R12_RDI + I_MOV_R13_RSI + \
        body + I_POP_R13 + I_POP_R12 + I_RET


def compile_program(text):
    """Compile whole JellyCore source to an ELF image (bytes)."""
    be = Backend()
    links_tokens = tokenize(text)
    # place blob, then links in order after it (16-byte aligned)
    image = bytearray(RT_BASE - BASE)      # header/globals gap
    image += be.blob
    while len(image) % 16:
        image.append(0)

    link_addrs = []
    for idx, toks in enumerate(links_tokens):
        chain = build_links(toks, idx, idx)
        ctx = CodegenContext(be, link_addrs)
        while len(image) % 16:
            image.append(0)
        addr = BASE + len(image)
        body = compile_link_body(chain, ctx)
        image += body
        link_addrs.append(addr)

    main_addr = link_addrs[-1]
    # patch main_ptr cell (inside blob) with the main link's address
    mp_fileoff = (be.sym["main_ptr"] - BASE)
    struct.pack_into("<Q", image, mp_fileoff, main_addr)

    filesz = len(image)
    entry = be.sym["_start"]
    eh = struct.pack("<4sBBBBB7xHHIQQQIHHHHHH",
                     b"\x7fELF", 2, 1, 1, 0, 0, 2, 0x3E, 1,
                     entry, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    ph = struct.pack("<IIQQQQQQ", 1, 7, 0, BASE, BASE, filesz, filesz, 0x1000)
    image[0:64] = eh
    image[64:64 + 56] = ph
    return bytes(image)


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
    if len(argv) == 3:
        src, out = argv[1], argv[2]
        try:
            image = compile_program(_read_source(src))
        except Unsupported as e:
            sys.exit(f"jellyc: unsupported construct: {e}")
        with open(out, "wb") as f:
            f.write(image)
        os.chmod(out, 0o755)
        return
    sys.exit("usage: jellyc.py [--check] SRC [OUT.elf]")


if __name__ == "__main__":
    main(sys.argv)
