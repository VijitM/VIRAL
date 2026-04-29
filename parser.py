"""
parser.py — PLY parser for portable typed assembly

Grammar (informal)
------------------
  program      : section*
  section      : directive statement*
  statement    : label_def
               | instruction
               | directive
  label_def    : IDENT type_suffix? COLON
  instruction  : OPCODE operand (COMMA operand)*
               | OPCODE                              # zero-operand e.g. ret, nop
  operand      : register
               | immediate
               | mem_ref
               | label_ref
  register     : REGISTER type_suffix?
  immediate    : HASH INT_LIT type_suffix?
               | HASH MINUS INT_LIT type_suffix?
               | HASH FLOAT_LIT type_suffix?
  mem_ref      : LBRACKET REGISTER (PLUS | MINUS) INT_LIT RBRACKET type_suffix?
               | LBRACKET REGISTER RBRACKET type_suffix?
  label_ref    : IDENT
  type_suffix  : COLON type_expr
  type_expr    : TYPE
               | ptr LANGLE type_expr RANGLE
"""

import ply.yacc as yacc
from lexer import tokens, lexer
from asm_ast import (
    Program, Section, LabelDef, Instruction, Directive,
    RegisterOperand, ImmediateOperand, LabelOperand, MemOperand,
    BaseType, PtrType, AsmType,
)
from typing import Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TYPE_MAP = {t.value: t for t in BaseType}

def _resolve_type(name: str) -> BaseType:
    if name not in _BASE_TYPE_MAP:
        raise ValueError(f"Unknown type: {name}")
    return _BASE_TYPE_MAP[name]

# Tracks sections being built
_current_program: Optional[Program] = None
_current_section: Optional[Section] = None


def _ensure_section(name=".text"):
    """Lazily create a section if none is active."""
    global _current_section, _current_program
    if _current_section is None:
        _current_section = Section(name=name)
        _current_program.sections.append(_current_section)


# ---------------------------------------------------------------------------
# Precedence (none needed for assembly, but PLY requires the declaration)
# ---------------------------------------------------------------------------

precedence = ()

# ---------------------------------------------------------------------------
# Grammar rules
# ---------------------------------------------------------------------------

def p_program(p):
    """program : statement_list"""
    p[0] = _current_program


def p_statement_list(p):
    """statement_list : statement_list statement
                      | statement
                      | statement_list NEWLINE
                      | NEWLINE"""
    pass   # side-effects happen inside each statement rule


def p_statement_directive(p):
    """statement : directive"""
    _ensure_section()
    _current_section.body.append(p[1])


def p_statement_label(p):
    """statement : label_def"""
    _ensure_section()
    _current_section.body.append(p[1])


def p_statement_instruction(p):
    """statement : instruction"""
    _ensure_section()
    _current_section.body.append(p[1])


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------

def p_directive_section(p):
    """directive : DIRECTIVE IDENT
                 | DIRECTIVE DIRECTIVE
                 | DIRECTIVE"""
    global _current_section, _current_program
    name = p[1]          # e.g. ".section"
    arg  = p[2] if len(p) == 3 else None

    if name == '.section' and arg:
        sec = _current_program.get_section(arg)
        if sec is None:
            sec = Section(name=arg)
            _current_program.sections.append(sec)
        _current_section = sec
        p[0] = Directive(name=name, args=[arg], lineno=p.lineno(1))
    else:
        args = [arg] if arg else []
        p[0] = Directive(name=name, args=args, lineno=p.lineno(1))


def p_directive_two_args(p):
    """directive : DIRECTIVE IDENT COMMA AT IDENT"""
    p[0] = Directive(name=p[1], args=[p[2], f"@{p[5]}"], lineno=p.lineno(1))


# ---------------------------------------------------------------------------
# Label definitions
# ---------------------------------------------------------------------------

def p_label_def_typed(p):
    """label_def : IDENT COLON type_expr COLON"""
    p[0] = LabelDef(name=p[1], type_ann=p[3], lineno=p.lineno(1))


def p_label_def(p):
    """label_def : IDENT COLON"""
    p[0] = LabelDef(name=p[1], lineno=p.lineno(1))


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

def p_instruction_with_operands(p):
    """instruction : OPCODE operand_list"""
    p[0] = Instruction(opcode=p[1], operands=p[2], lineno=p.lineno(1))


def p_instruction_no_operands(p):
    """instruction : OPCODE"""
    p[0] = Instruction(opcode=p[1], operands=[], lineno=p.lineno(1))


def p_operand_list(p):
    """operand_list : operand_list COMMA operand
                    | operand"""
    if len(p) == 4:
        p[0] = p[1] + [p[3]]
    else:
        p[0] = [p[1]]


# ---------------------------------------------------------------------------
# Operands
# ---------------------------------------------------------------------------

def p_operand_register(p):
    """operand : REGISTER COLON type_expr
               | REGISTER"""
    ann = p[3] if len(p) == 4 else None
    p[0] = RegisterOperand(name=p[1], type_ann=ann)


def p_operand_immediate_pos(p):
    """operand : HASH INT_LIT COLON type_expr
               | HASH INT_LIT"""
    ann = p[4] if len(p) == 5 else None
    p[0] = ImmediateOperand(value=p[2], type_ann=ann)


def p_operand_immediate_neg(p):
    """operand : HASH MINUS INT_LIT COLON type_expr
               | HASH MINUS INT_LIT"""
    ann = p[5] if len(p) == 6 else None
    p[0] = ImmediateOperand(value=-p[3], type_ann=ann)


def p_operand_mem_with_offset(p):
    """operand : LBRACKET REGISTER PLUS  INT_LIT RBRACKET COLON type_expr
               | LBRACKET REGISTER MINUS INT_LIT RBRACKET COLON type_expr
               | LBRACKET REGISTER PLUS  INT_LIT RBRACKET
               | LBRACKET REGISTER MINUS INT_LIT RBRACKET"""
    sign   = 1 if p[3] == '+' else -1
    offset = sign * p[4]
    ann    = p[7] if len(p) == 8 else None
    p[0]   = MemOperand(base=p[2], offset=offset, type_ann=ann)


def p_operand_mem_no_offset(p):
    """operand : LBRACKET REGISTER RBRACKET COLON type_expr
               | LBRACKET REGISTER RBRACKET"""
    ann  = p[5] if len(p) == 6 else None
    p[0] = MemOperand(base=p[2], offset=0, type_ann=ann)


def p_operand_label_ref(p):
    """operand : IDENT"""
    p[0] = LabelOperand(name=p[1])


# ---------------------------------------------------------------------------
# Type expressions
# ---------------------------------------------------------------------------

def p_type_expr_base(p):
    """type_expr : TYPE"""
    p[0] = _resolve_type(p[1])


def p_type_expr_ptr(p):
    """type_expr : TYPE LANGLE type_expr RANGLE"""
    if p[1] != 'ptr':
        raise SyntaxError(f"Expected 'ptr' before '<', got '{p[1]}'")
    p[0] = PtrType(inner=p[3])


# ---------------------------------------------------------------------------
# Error recovery
# ---------------------------------------------------------------------------

def p_error(p):
    if p:
        print(f"[Parser] Syntax error at {p.value!r} (line {p.lineno}, type {p.type})")
    else:
        print("[Parser] Syntax error at end of input")


# ---------------------------------------------------------------------------
# Build & public API
# ---------------------------------------------------------------------------

parser = yacc.yacc()


def parse(source: str) -> Program:
    global _current_program, _current_section
    _current_program = Program()
    _current_section = None
    lexer.lineno = 1
    parser.parse(source, lexer=lexer, tracking=True)
    return _current_program


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
    store [rsp + 8]:i32, r2
    call print_int
    ret
"""
    prog = parse(sample)
    for sec in prog.sections:
        print(f"Section: {sec.name}")
        for stmt in sec.body:
            print(" ", stmt)
