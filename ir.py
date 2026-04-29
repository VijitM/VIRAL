"""
ir.py — Architecture-neutral typed IR

Design
------
  - Infinite virtual registers (no physical register constraints)
  - Every value has an explicit type
  - Three-address form: dst = op(src1, src2)
  - Explicit control flow via jumps and labels
  - SSA-lite: we don't enforce SSA but the form supports it

IR Instruction set
------------------
  COPY   dst, src              -- register copy / move
  ADD    dst, src1, src2
  SUB    dst, src1, src2
  MUL    dst, src1, src2
  DIV    dst, src1, src2
  MOD    dst, src1, src2
  AND    dst, src1, src2
  OR     dst, src1, src2
  XOR    dst, src1, src2
  NOT    dst, src
  SHL    dst, src, amount
  SHR    dst, src, amount       -- logical shift right
  SAR    dst, src, amount       -- arithmetic shift right
  CMP    dst, src1, src2        -- dst is bool result
  LOAD   dst, addr              -- load from memory address
  STORE  addr, src              -- store to memory address
  LEA    dst, label             -- load effective address of label
  CALL   dst, fn, [args...]     -- call function, dst = return value
  RET    [src]                  -- return optional value
  JMP    label                  -- unconditional jump
  JIF    cond, true_lbl, false_lbl  -- conditional branch
  PUSH   src
  POP    dst
  NOP
  HLT
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Types (reuse from ast but redefined here so IR is self-contained)
# ---------------------------------------------------------------------------

class IRType(Enum):
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
    PTR  = "ptr"    # generic pointer (width is target-dependent)

    def byte_size(self) -> int:
        return {
            'i8': 1, 'u8': 1,
            'i16': 2, 'u16': 2,
            'i32': 4, 'u32': 4, 'f32': 4,
            'i64': 8, 'u64': 8, 'f64': 8,
            'bool': 1,
            'void': 0,
            'ptr': 8,    # assume 64-bit targets
        }[self.value]

    def is_integer(self) -> bool:
        return self in {
            IRType.I8, IRType.I16, IRType.I32, IRType.I64,
            IRType.U8, IRType.U16, IRType.U32, IRType.U64,
            IRType.BOOL, IRType.PTR,
        }

    def is_float(self) -> bool:
        return self in {IRType.F32, IRType.F64}

    def is_signed(self) -> bool:
        return self in {IRType.I8, IRType.I16, IRType.I32, IRType.I64}


# ---------------------------------------------------------------------------
# Values — the operands of IR instructions
# ---------------------------------------------------------------------------

@dataclass
class VReg:
    """Virtual register — infinite supply, each has a type."""
    id: int
    type: IRType

    def __str__(self):
        return f"%{self.id}:{self.type.value}"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, VReg) and self.id == other.id


@dataclass
class Immediate:
    value: Union[int, float]
    type: IRType

    def __str__(self):
        return f"#{self.value}:{self.type.value}"


@dataclass
class LabelRef:
    name: str

    def __str__(self):
        return f"@{self.name}"


IRValue = Union[VReg, Immediate, LabelRef]


# ---------------------------------------------------------------------------
# IR opcodes
# ---------------------------------------------------------------------------

class IROp(Enum):
    COPY  = "copy"
    ADD   = "add"
    SUB   = "sub"
    MUL   = "mul"
    DIV   = "div"
    MOD   = "mod"
    AND   = "and"
    OR    = "or"
    XOR   = "xor"
    NOT   = "not"
    SHL   = "shl"
    SHR   = "shr"
    SAR   = "sar"
    CMP   = "cmp"
    LOAD  = "load"
    STORE = "store"
    LEA   = "lea"
    CALL  = "call"
    RET   = "ret"
    JMP   = "jmp"
    JIF   = "jif"
    PUSH  = "push"
    POP   = "pop"
    NOP   = "nop"
    HLT   = "hlt"
    LABEL = "label"    # pseudo-op marking a label position


# ---------------------------------------------------------------------------
# IR instructions
# ---------------------------------------------------------------------------

@dataclass
class IRInstr:
    op:      IROp
    dst:     Optional[VReg]       = None
    srcs:    List[IRValue]        = field(default_factory=list)
    label:   Optional[str]        = None   # for LABEL, JMP, JIF, LEA
    label2:  Optional[str]        = None   # false branch for JIF
    lineno:  int                  = 0

    def __str__(self):
        parts = []
        if self.op == IROp.LABEL:
            return f"{self.label}:"
        if self.dst:
            parts.append(f"{self.dst} =")
        parts.append(self.op.value)
        parts.extend(str(s) for s in self.srcs)
        if self.label:
            parts.append(f"@{self.label}")
        if self.label2:
            parts.append(f"@{self.label2}")
        return "  " + " ".join(parts)


# ---------------------------------------------------------------------------
# IR basic block and function
# ---------------------------------------------------------------------------

@dataclass
class IRBlock:
    """A labelled sequence of instructions ending in a terminator."""
    label:  str
    instrs: List[IRInstr] = field(default_factory=list)

    def append(self, instr: IRInstr):
        self.instrs.append(instr)

    def __str__(self):
        lines = [f"{self.label}:"]
        lines.extend(str(i) for i in self.instrs)
        return "\n".join(lines)


@dataclass
class IRFunction:
    name:   str
    blocks: List[IRBlock] = field(default_factory=list)
    params: List[VReg]    = field(default_factory=list)
    ret_type: IRType      = IRType.VOID

    def __str__(self):
        header = f"fn {self.name}({', '.join(str(p) for p in self.params)}) -> {self.ret_type.value}"
        body   = "\n".join(str(b) for b in self.blocks)
        return f"{header} {{\n{body}\n}}"


@dataclass
class IRModule:
    """Top-level IR container — one per source file."""
    functions: List[IRFunction] = field(default_factory=list)
    globals:   List[IRInstr]    = field(default_factory=list)   # data section items

    def __str__(self):
        parts = []
        if self.globals:
            parts.append("; globals")
            parts.extend(str(g) for g in self.globals)
        parts.extend(str(f) for f in self.functions)
        return "\n\n".join(parts)
