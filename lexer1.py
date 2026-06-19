"""
lexer.py — PLY lexer for portable typed assembly

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

import ply.lex as lex

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
for op in OPCODES:
    reserved[op] = 'OPCODE'
for t in TYPES:
    reserved[t] = 'TYPE'

# ---------------------------------------------------------------------------
# Token list
# ---------------------------------------------------------------------------

tokens = [
    'REGISTER',       # r0, r1 … r15, rsp, rbp, rip (virtual regs)
    'IDENT',          # labels, section names, symbol names
    'INT_LIT',        # 42  0xFF  0b1010
    'FLOAT_LIT',      # 3.14
    'STRING_LIT',     # "hello"
    'DIRECTIVE',      # .section  .global  etc.
    'COLON',          # :
    'COMMA',          # ,
    'LBRACKET',       # [
    'RBRACKET',       # ]
    'LANGLE',         # <
    'RANGLE',         # >
    'HASH',           # #  (prefix for immediates)
    'PLUS',           # +
    'MINUS',          # -
    'AT',             # @  (used in .type foo, @function)
    'NEWLINE',
] + list(set(reserved.values()))   # OPCODE, TYPE

# ---------------------------------------------------------------------------
# Simple single-character tokens
# ---------------------------------------------------------------------------

t_COLON    = r':'
t_COMMA    = r','
t_LBRACKET = r'\['
t_RBRACKET = r'\]'
t_LANGLE   = r'<'
t_RANGLE   = r'>'
t_HASH     = r'\#'
t_PLUS     = r'\+'
t_MINUS    = r'-'
t_AT       = r'@'

# ---------------------------------------------------------------------------
# Ignored characters (spaces, tabs — NOT newlines)
# ---------------------------------------------------------------------------

t_ignore = ' \t'

# ---------------------------------------------------------------------------
# Rules with actions (order matters: longer rules first)
# ---------------------------------------------------------------------------

def t_COMMENT(t):
    r';[^\n]*'
    pass   # discard — use ; for comments, # is reserved for immediates

def t_DIRECTIVE(t):
    r'\.[a-zA-Z_][a-zA-Z0-9_]*'
    return t

def t_FLOAT_LIT(t):
    r'\d+\.\d+([eE][+-]?\d+)?'
    t.value = float(t.value)
    return t

def t_INT_LIT(t):
    r'0[xX][0-9a-fA-F]+|0[bB][01]+|\d+'
    base = 16 if '0x' in t.value.lower() and t.value.lower().startswith('0x') else \
           2  if '0b' in t.value.lower() and t.value.lower().startswith('0b') else 10
    t.value = int(t.value, base)
    return t

def t_STRING_LIT(t):
    r'"([^"\\]|\\.)*"'
    t.value = t.value[1:-1]   # strip quotes
    return t

def t_REGISTER(t):
    r'r(?:1[0-5]|[0-9])|rsp|rbp|rip|fp|sp|lr|pc|zero'
    return t

def t_IDENT(t):
    r'[a-zA-Z_][a-zA-Z0-9_]*'
    t.type = reserved.get(t.value, 'IDENT')
    return t

def t_NEWLINE(t):
    r'\n+'
    t.lexer.lineno += len(t.value)
    return t

def t_error(t):
    print(f"[Lexer] Illegal character {t.value[0]!r} at line {t.lexer.lineno}")
    t.lexer.skip(1)

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

lexer = lex.lex()


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
