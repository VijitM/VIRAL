"""
ast.py — AST node definitions for portable typed assembly
"""

from dataclasses import dataclass, field
from typing import Optional, List, Union
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Type system
# ---------------------------------------------------------------------------

class BaseType(Enum):
    I8   = "i8"
    I16  = "i16"
    I32  = "i32"
    I64  = "i64"
    U8   = "u8"
    U16  = "u16"
    U32  = "u32"
    U64  = "u64"
    F32  = "f32"
    F64  = "f64"
    BOOL = "bool"
    VOID = "void"

@dataclass
class PtrType:
    """Pointer to another type, e.g. ptr<i32>"""
    inner: Union[BaseType, "PtrType"]

    def __str__(self):
        return f"ptr<{self.inner}>"

AsmType = Union[BaseType, PtrType]


# ---------------------------------------------------------------------------
# Operands
# ---------------------------------------------------------------------------

@dataclass
class RegisterOperand:
    name: str               # e.g. "r0", "rsp"
    type_ann: Optional[AsmType] = None   # explicit annotation if present

@dataclass
class ImmediateOperand:
    value: int
    type_ann: Optional[AsmType] = None

@dataclass
class LabelOperand:
    name: str               # reference to a label, e.g. in jump targets

@dataclass
class MemOperand:
    """[base + offset], base is a register name"""
    base: str
    offset: int = 0
    type_ann: Optional[AsmType] = None

Operand = Union[RegisterOperand, ImmediateOperand, LabelOperand, MemOperand]


# ---------------------------------------------------------------------------
# Instructions & directives
# ---------------------------------------------------------------------------

@dataclass
class Instruction:
    opcode: str
    operands: List[Operand] = field(default_factory=list)
    lineno: int = 0

@dataclass
class LabelDef:
    name: str
    type_ann: Optional[AsmType] = None   # optional type for typed entry points
    lineno: int = 0

@dataclass
class Directive:
    """
    Assembler directives, e.g.:
      .section .text
      .global main
      .type   my_fn, @function
    """
    name: str                            # e.g. "section", "global", "type"
    args: List[str] = field(default_factory=list)
    lineno: int = 0


# ---------------------------------------------------------------------------
# Top-level program
# ---------------------------------------------------------------------------

Statement = Union[Instruction, LabelDef, Directive]

@dataclass
class Section:
    name: str                            # ".text", ".data", ".bss"
    body: List[Statement] = field(default_factory=list)

@dataclass
class Program:
    sections: List[Section] = field(default_factory=list)

    def get_section(self, name: str) -> Optional[Section]:
        for s in self.sections:
            if s.name == name:
                return s
        return None
