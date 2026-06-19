"""
lexer.py — Pure-Python lexer for portable typed assembly
         (drop-in replacement for the PLY-based original)

Token categories
----------------
  Opcodes     : mov, add, sub, mul, div, jmp, je, jne, call, ret, push, pop,
                load, store, cmp, and, or, xor, not, shl, shr
  Types       : i8 i16 i32 i64 u8 u16 u32 u64 f32 f64 bool void ptr
  Directives  : .section .global .type .extern .byte .word .long .quad .string
  Misc        : IDENT, INT_LIT, FLOAT_LIT, STRING_LIT, REGISTER,
                COLON, COMMA, LBRACKET, RBRACKET, LANGLE, RANGLE,
                HASH, PLUS, MINUS, NEWLINE, COMMENT
"""

import re

# ---------------------------------------------------------------------------
# Reserved words — checked inside t_IDENT so they shadow IDENT
# ---------------------------------------------------------------------------

OPCODES = {
    'mov', 'add', 'sub', 'mul', 'div', 'mod',
    'jmp', 'je', 'jne', 'jlt', 'jle', 'jgt', 'jge',
    'call', 'ret', 'push', 'pop',
    'load', 'store',
    'cmp',
    'and', 'or', 'xor', 'not',
    'shl', 'shr', 'sar',
    'lea', 'nop', 'hlt',
}

TYPES = {
    'i8', 'i16', 'i32', 'i64',
    'u8', 'u16', 'u32', 'u64',
    'f32', 'f64',
    'bool', 'void', 'ptr',
}

reserved = {}
for _op in OPCODES:
    reserved[_op] = 'OPCODE'
for _t in TYPES:
    reserved[_t] = 'TYPE'

# ---------------------------------------------------------------------------
# Token list (kept for reference / compatibility with callers that import it)
# ---------------------------------------------------------------------------

tokens = [
    'REGISTER',
    'IDENT',
    'INT_LIT',
    'FLOAT_LIT',
    'STRING_LIT',
    'DIRECTIVE',
    'COLON',
    'COMMA',
    'LBRACKET',
    'RBRACKET',
    'LANGLE',
    'RANGLE',
    'HASH',
    'PLUS',
    'MINUS',
    'AT',
    'NEWLINE',
] + list(set(reserved.values()))   # OPCODE, TYPE

# ---------------------------------------------------------------------------
# Master regex  —  order mirrors PLY priority rules:
#   1. Function-based rules in definition order (longer / more specific first)
#   2. String rules sorted by decreasing pattern length
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    # Comments  (;  …  end-of-line) — captured so we can discard them
    (?P<COMMENT>    ;[^\n]*                                         )
    # Directives   .foo
  | (?P<DIRECTIVE>  \.[a-zA-Z_][a-zA-Z0-9_]*                       )
    # Float literals  (must come before INT so "3.14" isn't "3" + ".14")
  | (?P<FLOAT_LIT>  \d+\.\d+(?:[eE][+-]?\d+)?                      )
    # Integer literals  hex / binary / decimal
  | (?P<INT_LIT>    0[xX][0-9a-fA-F]+|0[bB][01]+|\d+               )
    # String literals   "…"  with escape sequences
  | (?P<STRING_LIT> "(?:[^"\\]|\\.)*"                               )
    # Registers  (must precede IDENT so "r0" is not tokenised as IDENT)
  | (?P<REGISTER>   r(?:1[0-5]|[0-9])|rsp|rbp|rip|fp|sp|lr|pc|zero )
    # Identifiers / reserved words
  | (?P<IDENT>      [a-zA-Z_][a-zA-Z0-9_]*                         )
    # Newlines  (one or more; we count them for lineno)
  | (?P<NEWLINE>    \n+                                             )
    # Single-character punctuation
  | (?P<COLON>      :  )
  | (?P<COMMA>      ,  )
  | (?P<LBRACKET>   \[ )
  | (?P<RBRACKET>   \] )
  | (?P<LANGLE>     <  )
  | (?P<RANGLE>     >  )
  | (?P<HASH>       \# )
  | (?P<PLUS>       \+ )
  | (?P<MINUS>      -  )
  | (?P<AT>         @  )
    # Ignored whitespace (spaces / tabs)
  | (?P<IGNORE>     [ \t]+                                          )
    # Anything else is an illegal character
  | (?P<ERROR>      .  )
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# LexToken  —  mirrors ply.lex.LexToken so downstream code is unaffected
# ---------------------------------------------------------------------------

class LexToken:
    """Minimal stand-in for ply.lex.LexToken."""
    __slots__ = ('type', 'value', 'lineno', 'lexpos')

    def __repr__(self):
        return f"LexToken({self.type},{self.value!r},{self.lineno},{self.lexpos})"


# ---------------------------------------------------------------------------
# Lexer  —  mirrors the ply.lex.Lexer public interface used by the project
# ---------------------------------------------------------------------------

class Lexer:
    """
    Drop-in replacement for the PLY lexer object.

    Public interface
    ----------------
    lexer.input(text)       — feed source text
    lexer.token()           — return the next LexToken or None
    iter(lexer)             — iterate over all tokens
    lexer.lineno            — current line number (1-based)
    """

    def __init__(self):
        self.lineno: int = 1
        self._tokens: list[LexToken] = []
        self._pos: int = 0

    # ------------------------------------------------------------------
    def input(self, text: str) -> None:
        """Tokenise *text* and reset the internal cursor."""
        self.lineno = 1
        self._tokens = list(self._tokenise(text))
        self._pos = 0

    # ------------------------------------------------------------------
    def token(self) -> LexToken | None:
        """Return the next token, or None at end-of-input."""
        if self._pos >= len(self._tokens):
            return None
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    # ------------------------------------------------------------------
    def __iter__(self):
        return self

    def __next__(self) -> LexToken:
        tok = self.token()
        if tok is None:
            raise StopIteration
        return tok

    # ------------------------------------------------------------------
    # Internal tokeniser
    # ------------------------------------------------------------------

    def _tokenise(self, text: str):
        lineno = 1

        for m in _TOKEN_RE.finditer(text):
            kind = m.lastgroup
            raw  = m.group()

            # ---- skip whitespace ----------------------------------------
            if kind == 'IGNORE':
                continue

            # ---- skip comments ------------------------------------------
            if kind == 'COMMENT':
                continue

            # ---- error / illegal character ------------------------------
            if kind == 'ERROR':
                print(f"[Lexer] Illegal character {raw!r} at line {lineno}")
                continue

            # ---- newlines (count but still emit) ------------------------
            if kind == 'NEWLINE':
                tok        = LexToken()
                tok.type   = 'NEWLINE'
                tok.value  = raw
                tok.lineno = lineno
                tok.lexpos = m.start()
                lineno    += len(raw)   # raw is one or more '\n'
                yield tok
                continue

            # ---- build token --------------------------------------------
            tok        = LexToken()
            tok.type   = kind
            tok.lineno = lineno
            tok.lexpos = m.start()

            # value conversions
            if kind == 'INT_LIT':
                low = raw.lower()
                base = 16 if low.startswith('0x') else \
                       2  if low.startswith('0b') else 10
                tok.value = int(raw, base)

            elif kind == 'FLOAT_LIT':
                tok.value = float(raw)

            elif kind == 'STRING_LIT':
                tok.value = raw[1:-1]   # strip surrounding quotes

            elif kind == 'IDENT':
                # promote reserved words to OPCODE / TYPE
                tok.type  = reserved.get(raw, 'IDENT')
                tok.value = raw

            else:
                tok.value = raw

            yield tok

        # update the public lineno so callers see the final line
        self.lineno = lineno


# ---------------------------------------------------------------------------
# Module-level lexer instance  —  matches PLY's  `lexer = lex.lex()`
# ---------------------------------------------------------------------------

lexer = Lexer()


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    sample = """\
.section .text
.global main

main:
    mov  r0:i32, #42
    mov  r1:i32, #10
    add  r2:i32, r0, r1
    store [rsp + -8]:i32, r2
    call print_int
    ret
"""
    lexer.input(sample)
    for tok in lexer:
        print(tok)
