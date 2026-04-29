"""
backend.py — Abstract backend base class

Every target backend inherits from Backend and implements:
  - emit_module(module) -> str      top-level entry point
  - emit_function(fn)   -> str
  - emit_instr(instr)   -> str

Register allocation is handled here in the base class using a simple
linear scan allocator over the virtual registers. Each backend provides
its physical register list and the allocator does the mapping.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from ir import (
    IRModule, IRFunction, IRBlock, IRInstr, IROp,
    IRType, VReg, Immediate, LabelRef, IRValue,
)


# ---------------------------------------------------------------------------
# Simple linear scan register allocator
# ---------------------------------------------------------------------------

class RegisterAllocator:
    """
    Maps VRegs to physical register names.
    Strategy: first-fit from the available pool.
    Spills to stack slots when registers are exhausted.
    """

    def __init__(self, int_regs: List[str], float_regs: List[str], ptr_size: int = 8):
        self._int_regs   = list(int_regs)
        self._float_regs = list(float_regs)
        self._ptr_size   = ptr_size
        self._mapping:   Dict[int, str] = {}    # vreg id → physical reg name
        self._spills:    Dict[int, int] = {}    # vreg id → stack offset
        self._stack_offset = 0
        self._used_int   = 0
        self._used_float = 0

    def assign(self, vreg: VReg) -> str:
        if vreg.id in self._mapping:
            return self._mapping[vreg.id]
        if vreg.id in self._spills:
            return self._spill_ref(vreg.id)

        if vreg.type.is_float():
            pool = self._float_regs
            used_attr = '_used_float'
        else:
            pool = self._int_regs
            used_attr = '_used_int'

        used = getattr(self, used_attr)
        if used < len(pool):
            phys = pool[used]
            setattr(self, used_attr, used + 1)
            self._mapping[vreg.id] = phys
            return phys
        else:
            # Spill to stack
            self._stack_offset += self._ptr_size
            self._spills[vreg.id] = self._stack_offset
            return self._spill_ref(vreg.id)

    def _spill_ref(self, vreg_id: int) -> str:
        offset = self._spills[vreg_id]
        return f"[sp-{offset}]"

    def resolve(self, value: IRValue) -> str:
        if isinstance(value, VReg):
            return self.assign(value)
        if isinstance(value, Immediate):
            return str(value.value)
        if isinstance(value, LabelRef):
            return value.name
        return str(value)

    @property
    def frame_size(self) -> int:
        return self._stack_offset


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------

class Backend(ABC):
    name: str = "unknown"

    # Each backend provides these lists
    INT_REGS:   List[str] = []
    FLOAT_REGS: List[str] = []

    def emit_module(self, module: IRModule) -> str:
        parts = [self.file_header()]
        if module.globals:
            parts.append(self.data_section_header())
            for g in module.globals:
                parts.append(self.emit_global(g))
        parts.append(self.text_section_header())
        for fn in module.functions:
            parts.append(self.emit_function(fn))
        return "\n".join(parts)

    def emit_function(self, fn: IRFunction) -> str:
        alloc  = RegisterAllocator(self.INT_REGS, self.FLOAT_REGS)
        # Pre-assign all VRegs seen in the function
        for blk in fn.blocks:
            for instr in blk.instrs:
                if instr.dst:
                    alloc.assign(instr.dst)
                for src in instr.srcs:
                    if isinstance(src, VReg):
                        alloc.assign(src)

        lines  = []
        lines.append(self.fn_prologue(fn.name, alloc.frame_size))
        for blk in fn.blocks:
            lines.append(self.emit_block(blk, alloc))
        lines.append(self.fn_epilogue(fn.name))
        return "\n".join(lines)

    def emit_block(self, block: IRBlock, alloc: RegisterAllocator) -> str:
        lines = [f"{block.label}:"]
        for instr in block.instrs:
            result = self.emit_instr(instr, alloc)
            if result:
                lines.append(result)
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Abstract methods — each backend must implement these
    # -----------------------------------------------------------------------

    @abstractmethod
    def emit_instr(self, instr: IRInstr, alloc: RegisterAllocator) -> str:
        """Translate one IR instruction to target assembly text."""

    @abstractmethod
    def fn_prologue(self, name: str, frame_size: int) -> str:
        """Function header + stack frame setup."""

    @abstractmethod
    def fn_epilogue(self, name: str) -> str:
        """Function footer."""

    @abstractmethod
    def file_header(self) -> str:
        """Top-of-file assembler directives."""

    @abstractmethod
    def text_section_header(self) -> str:

        """Directive to begin the text section."""

    @abstractmethod
    def data_section_header(self) -> str:
        """Directive to begin the data section."""

    @abstractmethod
    def emit_global(self, instr: IRInstr) -> str:
        """Emit a global data item."""

    # -----------------------------------------------------------------------
    # Shared helpers
    # -----------------------------------------------------------------------

    def _indent(self, s: str, n: int = 4) -> str:
        return " " * n + s

    def _comment(self, s: str) -> str:
        return f"    ; {s}"
