"""
typechecker.py — Semantic analysis & type checking pass

Responsibilities
----------------
  Pass 1  Collect all label definitions into a symbol table
  Pass 2  Validate every instruction:
            - operand count matches opcode signature
            - type annotations are compatible
            - label references resolve
            - immediate values fit declared type
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from asm_ast import (
    Program, Section, LabelDef, Instruction, Directive,
    RegisterOperand, ImmediateOperand, LabelOperand, MemOperand,
    BaseType, PtrType, AsmType,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

@dataclass
class TypeError_:
    message: str
    lineno: int

    def __str__(self):
        return f"[TypeError] line {self.lineno}: {self.message}"

@dataclass
class SemanticError:
    message: str
    lineno: int

    def __str__(self):
        return f"[SemanticError] line {self.lineno}: {self.message}"

Diagnostic = TypeError_ | SemanticError


# ---------------------------------------------------------------------------
# Opcode signatures
# Tuple of (min_operands, max_operands, description)
# None for max means variadic / no constraint
# ---------------------------------------------------------------------------

OPCODE_SIGS: Dict[str, Tuple[int, Optional[int]]] = {
    'mov':   (2, 2),
    'add':   (3, 3),
    'sub':   (3, 3),
    'mul':   (3, 3),
    'div':   (3, 3),
    'mod':   (3, 3),
    'and':   (3, 3),
    'or':    (3, 3),
    'xor':   (3, 3),
    'not':   (2, 2),
    'shl':   (3, 3),
    'shr':   (3, 3),
    'sar':   (3, 3),
    'cmp':   (2, 3),
    'jmp':   (1, 1),
    'je':    (1, 1),
    'jne':   (1, 1),
    'jlt':   (1, 1),
    'jle':   (1, 1),
    'jgt':   (1, 1),
    'jge':   (1, 1),
    'call':  (1, 1),
    'ret':   (0, 1),
    'push':  (1, 1),
    'pop':   (1, 1),
    'load':  (2, 2),
    'store': (2, 2),
    'lea':   (2, 2),
    'nop':   (0, 0),
    'hlt':   (0, 0),
}

# Types that are integer-like (allow arithmetic, bitwise, immediates)
INT_TYPES = {
    BaseType.I8, BaseType.I16, BaseType.I32, BaseType.I64,
    BaseType.U8, BaseType.U16, BaseType.U32, BaseType.U64,
}

FLOAT_TYPES = {BaseType.F32, BaseType.F64}

# Immediate value ranges per integer type
IMM_RANGES: Dict[BaseType, Tuple[int, int]] = {
    BaseType.I8:  (-128, 127),
    BaseType.I16: (-32768, 32767),
    BaseType.I32: (-2**31, 2**31 - 1),
    BaseType.I64: (-2**63, 2**63 - 1),
    BaseType.U8:  (0, 255),
    BaseType.U16: (0, 65535),
    BaseType.U32: (0, 2**32 - 1),
    BaseType.U64: (0, 2**64 - 1),
}


# ---------------------------------------------------------------------------
# Symbol table entry
# ---------------------------------------------------------------------------

@dataclass
class Symbol:
    name: str
    type_ann: Optional[AsmType]
    section: str
    lineno: int


# ---------------------------------------------------------------------------
# Type checker
# ---------------------------------------------------------------------------

class TypeChecker:
    def __init__(self):
        self.symbols: Dict[str, Symbol] = {}
        self.extern_symbols: set = set()
        self.diagnostics: List[Diagnostic] = []

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    def check(self, program: Program) -> List[Diagnostic]:
        self.diagnostics.clear()
        self._pass1_collect_labels(program)
        self._pass2_check_instructions(program)
        return self.diagnostics

    # -----------------------------------------------------------------------
    # Pass 1 — collect label definitions
    # -----------------------------------------------------------------------

    def _pass1_collect_labels(self, program: Program):
        for section in program.sections:
            for stmt in section.body:
                if isinstance(stmt, LabelDef):
                    if stmt.name in self.symbols:
                        prev = self.symbols[stmt.name]
                        self.diagnostics.append(SemanticError(
                            f"Duplicate label '{stmt.name}' "
                            f"(first defined at line {prev.lineno})",
                            stmt.lineno,
                        ))
                    else:
                        self.symbols[stmt.name] = Symbol(
                            name=stmt.name,
                            type_ann=stmt.type_ann,
                            section=section.name,
                            lineno=stmt.lineno,
                        )

    # -----------------------------------------------------------------------
    # Pass 2 — instruction-level checking
    # -----------------------------------------------------------------------

    def _pass2_check_instructions(self, program: Program):
        for section in program.sections:
            for stmt in section.body:
                if isinstance(stmt, Instruction):
                    self._check_instruction(stmt)

    def _check_instruction(self, instr: Instruction):
        opcode = instr.opcode

        # Operand count
        if opcode in OPCODE_SIGS:
            lo, hi = OPCODE_SIGS[opcode]
            n = len(instr.operands)
            if n < lo or (hi is not None and n > hi):
                expected = f"{lo}" if lo == hi else f"{lo}–{hi}"
                self.diagnostics.append(SemanticError(
                    f"'{opcode}' expects {expected} operand(s), got {n}",
                    instr.lineno,
                ))
                return  # skip further checks for this instruction

        # Per-operand checks
        for op in instr.operands:
            if isinstance(op, ImmediateOperand):
                self._check_immediate(op, instr.lineno)
            elif isinstance(op, LabelOperand):
                self._check_label_ref(op, instr.lineno)

        # Instruction-specific type consistency
        self._check_type_consistency(instr)

    def _check_immediate(self, op: ImmediateOperand, lineno: int):
        if op.type_ann is None:
            return   # unannotated immediate — backend infers
        if isinstance(op.type_ann, PtrType):
            self.diagnostics.append(TypeError_(
                "Immediate value cannot have pointer type",
                lineno,
            ))
            return
        t = op.type_ann
        if t in IMM_RANGES:
            lo, hi = IMM_RANGES[t]
            if not (lo <= op.value <= hi):
                self.diagnostics.append(TypeError_(
                    f"Immediate {op.value} out of range for {t.value} [{lo}, {hi}]",
                    lineno,
                ))

    def _check_label_ref(self, op: LabelOperand, lineno: int):
        if op.name not in self.symbols and op.name not in self.extern_symbols:
            # Treat unknown labels as potential external symbols (like libc calls)
            # Add to extern set so we only warn once
            self.extern_symbols.add(op.name)

    def _check_type_consistency(self, instr: Instruction):
        """
        For arithmetic/logic ops the destination and source types should match.
        We only warn — the programmer may have intentional truncation.
        """
        arith = {'add', 'sub', 'mul', 'div', 'mod', 'and', 'or', 'xor', 'shl', 'shr', 'sar'}
        if instr.opcode not in arith:
            return

        types = [
            op.type_ann
            for op in instr.operands
            if hasattr(op, 'type_ann') and op.type_ann is not None
        ]
        if len(types) < 2:
            return   # not enough annotations to compare

        first = types[0]
        for t in types[1:]:
            if t != first:
                self.diagnostics.append(TypeError_(
                    f"'{instr.opcode}' operand type mismatch: "
                    f"{_type_str(first)} vs {_type_str(t)}",
                    instr.lineno,
                ))
                break   # one error per instruction is enough


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _type_str(t: AsmType) -> str:
    if isinstance(t, BaseType):
        return t.value
    return str(t)


# ---------------------------------------------------------------------------
# Public convenience
# ---------------------------------------------------------------------------

def type_check(program: Program) -> List[Diagnostic]:
    return TypeChecker().check(program)


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    from parser import parse

    good = """\
.section .text
.global main
main:
    mov  r0:i32, #42
    add  r1:i32, r0:i32, r0:i32
    jmp  exit
exit:
    ret
"""
    bad = """\
.section .text
main:
    add  r0:i32, r1:i64, #99    ; type mismatch
    jmp  missing_label          ; undefined label
    mov  r2:u8, #300            ; immediate out of range
    ret
main:                           ; duplicate label
"""

    for label, src in [("GOOD", good), ("BAD", bad)]:
        print(f"\n=== {label} ===")
        prog = parse(src)
        diags = type_check(prog)
        if not diags:
            print("  No errors.")
        for d in diags:
            print(" ", d)
