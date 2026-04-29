"""
ir_lower.py — AST → IR lowering pass

Responsibilities
----------------
  - Map source virtual registers (r0–r15) to IR VRegs
  - Translate every opcode to its IR equivalent
  - Handle label definitions and jump targets
  - Translate type annotations to IRType
  - Group instructions into basic blocks (split at labels and jumps)
  - Collect functions from .text, data items from .data/.bss
"""

from typing import Dict, Optional, List
from asm_ast import (
    Program, Section, LabelDef, Instruction, Directive,
    RegisterOperand, ImmediateOperand, LabelOperand, MemOperand,
    BaseType, PtrType, AsmType,
)
from ir import (
    IRModule, IRFunction, IRBlock, IRInstr, IROp,
    IRType, VReg, Immediate, LabelRef, IRValue,
)


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

_AST_TO_IR: Dict[str, IRType] = {t.value: t for t in IRType}

def _to_ir_type(t: Optional[AsmType]) -> IRType:
    if t is None:
        return IRType.I64          # default: 64-bit integer
    if isinstance(t, PtrType):
        return IRType.PTR
    return _AST_TO_IR.get(t.value, IRType.I64)


# ---------------------------------------------------------------------------
# Opcode mapping  source opcode → IROp
# ---------------------------------------------------------------------------

_OPCODE_MAP: Dict[str, IROp] = {
    'mov':   IROp.COPY,
    'add':   IROp.ADD,
    'sub':   IROp.SUB,
    'mul':   IROp.MUL,
    'div':   IROp.DIV,
    'mod':   IROp.MOD,
    'and':   IROp.AND,
    'or':    IROp.OR,
    'xor':   IROp.XOR,
    'not':   IROp.NOT,
    'shl':   IROp.SHL,
    'shr':   IROp.SHR,
    'sar':   IROp.SAR,
    'cmp':   IROp.CMP,
    'load':  IROp.LOAD,
    'store': IROp.STORE,
    'lea':   IROp.LEA,
    'call':  IROp.CALL,
    'ret':   IROp.RET,
    'jmp':   IROp.JMP,
    'je':    IROp.JIF,
    'jne':   IROp.JIF,
    'jlt':   IROp.JIF,
    'jle':   IROp.JIF,
    'jgt':   IROp.JIF,
    'jge':   IROp.JIF,
    'push':  IROp.PUSH,
    'pop':   IROp.POP,
    'nop':   IROp.NOP,
    'hlt':   IROp.HLT,
}

# Conditional jump opcodes — need special handling
_COND_JUMPS = {'je', 'jne', 'jlt', 'jle', 'jgt', 'jge'}


# ---------------------------------------------------------------------------
# Lowering context
# ---------------------------------------------------------------------------

class LoweringContext:
    def __init__(self):
        self._vreg_counter  = 0
        self._reg_map: Dict[str, VReg] = {}   # source reg name → VReg

    def vreg(self, type: IRType) -> VReg:
        """Allocate a fresh virtual register."""
        v = VReg(id=self._vreg_counter, type=type)
        self._vreg_counter += 1
        return v

    def get_or_create_reg(self, name: str, type: IRType) -> VReg:
        """
        Map a source register name to a VReg.
        If the same name is seen again with a different type, the type
        from the first annotation wins — this mirrors how a real register
        file works (one physical register, one width).
        """
        if name not in self._reg_map:
            self._reg_map[name] = self.vreg(type)
        return self._reg_map[name]


# ---------------------------------------------------------------------------
# Lowering operands
# ---------------------------------------------------------------------------

def _lower_operand(op, ctx: LoweringContext, default_type: IRType = IRType.I64) -> IRValue:
    if isinstance(op, RegisterOperand):
        t = _to_ir_type(op.type_ann) if op.type_ann else default_type
        return ctx.get_or_create_reg(op.name, t)

    if isinstance(op, ImmediateOperand):
        t = _to_ir_type(op.type_ann) if op.type_ann else default_type
        return Immediate(value=op.value, type=t)

    if isinstance(op, LabelOperand):
        return LabelRef(name=op.name)

    if isinstance(op, MemOperand):
        # Memory operands lower to a LabelRef or computed address.
        # The backend handles the actual addressing mode.
        t = _to_ir_type(op.type_ann) if op.type_ann else default_type
        base_vreg = ctx.get_or_create_reg(op.base, IRType.PTR)
        return base_vreg   # offset is encoded separately in LOAD/STORE

    raise ValueError(f"Unknown operand type: {type(op)}")


# ---------------------------------------------------------------------------
# Block builder — splits instruction stream at labels and terminators
# ---------------------------------------------------------------------------

class BlockBuilder:
    def __init__(self, fn: IRFunction):
        self._fn       = fn
        self._current  : Optional[IRBlock] = None
        self._block_idx = 0

    def _new_block(self, label: str) -> IRBlock:
        blk = IRBlock(label=label)
        self._fn.blocks.append(blk)
        self._current = blk
        return blk

    def ensure_block(self, label: str = None):
        if self._current is None:
            lbl = label or f"__bb{self._block_idx}"
            self._block_idx += 1
            self._new_block(lbl)

    def start_block(self, label: str):
        self._new_block(label)

    def emit(self, instr: IRInstr):
        self.ensure_block()
        self._current.instrs.append(instr)

    def is_terminated(self) -> bool:
        if not self._current or not self._current.instrs:
            return False
        last_op = self._current.instrs[-1].op
        return last_op in {IROp.RET, IROp.JMP, IROp.JIF, IROp.HLT}


# ---------------------------------------------------------------------------
# Main lowering pass
# ---------------------------------------------------------------------------

class IRLowerer:
    def __init__(self):
        self.errors: List[str] = []

    def lower(self, program: Program) -> IRModule:
        module = IRModule()
        for section in program.sections:
            if section.name in ('.text', 'text'):
                self._lower_text_section(section, module)
            elif section.name in ('.data', '.bss', 'data', 'bss'):
                self._lower_data_section(section, module)
        return module

    # -----------------------------------------------------------------------
    # Text section — produces IRFunctions
    # -----------------------------------------------------------------------

    def _lower_text_section(self, section: Section, module: IRModule):
        # Group statements into functions, splitting at each top-level label.
        # Each label that isn't inside a function starts a new function.
        current_fn: Optional[IRFunction]  = None
        builder:    Optional[BlockBuilder] = None
        ctx:        Optional[LoweringContext] = None

        for stmt in section.body:

            if isinstance(stmt, LabelDef):
                # A new label — either starts a new function or a new block
                # within the current function. We treat every top-level label
                # as a function entry point for simplicity.
                ctx        = LoweringContext()
                current_fn = IRFunction(name=stmt.name)
                module.functions.append(current_fn)
                builder    = BlockBuilder(current_fn)
                builder.start_block(stmt.name)

            elif isinstance(stmt, Instruction):
                if current_fn is None:
                    # Instructions before any label — create implicit main block
                    ctx        = LoweringContext()
                    current_fn = IRFunction(name="__anon")
                    module.functions.append(current_fn)
                    builder    = BlockBuilder(current_fn)
                    builder.ensure_block("__entry")

                self._lower_instruction(stmt, builder, ctx)

            elif isinstance(stmt, Directive):
                pass   # directives in .text are metadata; backend handles them

    def _lower_instruction(self, instr: Instruction, builder: BlockBuilder, ctx: LoweringContext):
        op     = instr.opcode
        lineno = instr.lineno
        ops    = instr.operands

        # Determine default type from first annotated operand
        default_type = IRType.I64
        for o in ops:
            if hasattr(o, 'type_ann') and o.type_ann:
                default_type = _to_ir_type(o.type_ann)
                break

        ir_op = _OPCODE_MAP.get(op)
        if ir_op is None:
            self.errors.append(f"Unknown opcode '{op}' at line {lineno}")
            return

        # ---- NOP / HLT ----
        if ir_op in (IROp.NOP, IROp.HLT):
            builder.emit(IRInstr(op=ir_op, lineno=lineno))
            return

        # ---- RET ----
        if ir_op == IROp.RET:
            src = _lower_operand(ops[0], ctx, default_type) if ops else None
            srcs = [src] if src else []
            builder.emit(IRInstr(op=IROp.RET, srcs=srcs, lineno=lineno))
            return

        # ---- Unconditional JMP ----
        if ir_op == IROp.JMP:
            target = ops[0]
            lbl    = target.name if isinstance(target, LabelOperand) else str(target)
            builder.emit(IRInstr(op=IROp.JMP, label=lbl, lineno=lineno))
            return

        # ---- Conditional jumps (je/jne/jlt etc.) ----
        # Source convention: the condition is the last CMP result (in cond vreg)
        # We encode as JIF cond, true_label.  The backend emits the right branch.
        if op in _COND_JUMPS:
            target = ops[0]
            lbl    = target.name if isinstance(target, LabelOperand) else str(target)
            # Use a synthetic condition vreg — the backend knows the flags context
            cond_vreg = ctx.vreg(IRType.BOOL)
            builder.emit(IRInstr(
                op=IROp.JIF,
                srcs=[cond_vreg],
                label=lbl,
                label2=op,    # encode the condition kind in label2 field
                lineno=lineno,
            ))
            return

        # ---- CALL ----
        if ir_op == IROp.CALL:
            fn_operand = ops[0]
            fn_ref     = _lower_operand(fn_operand, ctx, default_type)
            arg_vregs  = [_lower_operand(o, ctx, default_type) for o in ops[1:]]
            dst        = ctx.vreg(default_type)
            builder.emit(IRInstr(
                op=IROp.CALL,
                dst=dst,
                srcs=[fn_ref] + arg_vregs,
                lineno=lineno,
            ))
            return

        # ---- PUSH / POP ----
        if ir_op == IROp.PUSH:
            src = _lower_operand(ops[0], ctx, default_type)
            builder.emit(IRInstr(op=IROp.PUSH, srcs=[src], lineno=lineno))
            return

        if ir_op == IROp.POP:
            dst = ctx.get_or_create_reg(ops[0].name, default_type) \
                  if isinstance(ops[0], RegisterOperand) else ctx.vreg(default_type)
            builder.emit(IRInstr(op=IROp.POP, dst=dst, lineno=lineno))
            return

        # ---- LOAD ----
        if ir_op == IROp.LOAD:
            dst     = ctx.get_or_create_reg(ops[0].name, default_type) \
                      if isinstance(ops[0], RegisterOperand) else ctx.vreg(default_type)
            addr    = _lower_operand(ops[1], ctx, IRType.PTR)
            offset  = ops[1].offset if isinstance(ops[1], MemOperand) else 0
            builder.emit(IRInstr(
                op=IROp.LOAD,
                dst=dst,
                srcs=[addr, Immediate(offset, IRType.I64)],
                lineno=lineno,
            ))
            return

        # ---- STORE ----
        if ir_op == IROp.STORE:
            addr   = _lower_operand(ops[0], ctx, IRType.PTR)
            offset = ops[0].offset if isinstance(ops[0], MemOperand) else 0
            src    = _lower_operand(ops[1], ctx, default_type)
            builder.emit(IRInstr(
                op=IROp.STORE,
                srcs=[addr, Immediate(offset, IRType.I64), src],
                lineno=lineno,
            ))
            return

        # ---- LEA ----
        if ir_op == IROp.LEA:
            dst = ctx.get_or_create_reg(ops[0].name, IRType.PTR) \
                  if isinstance(ops[0], RegisterOperand) else ctx.vreg(IRType.PTR)
            lbl = ops[1].name if isinstance(ops[1], LabelOperand) else str(ops[1])
            builder.emit(IRInstr(op=IROp.LEA, dst=dst, label=lbl, lineno=lineno))
            return

        # ---- Standard 2/3-operand arithmetic & logic ----
        # Format: OPCODE dst, src1 [, src2]
        if len(ops) >= 2:
            dst_op = ops[0]
            dst    = ctx.get_or_create_reg(dst_op.name, default_type) \
                     if isinstance(dst_op, RegisterOperand) else ctx.vreg(default_type)
            srcs   = [_lower_operand(o, ctx, default_type) for o in ops[1:]]
            builder.emit(IRInstr(op=ir_op, dst=dst, srcs=srcs, lineno=lineno))
            return

        # ---- Single-operand (NOT, etc.) ----
        if len(ops) == 1:
            dst_op = ops[0]
            dst    = ctx.get_or_create_reg(dst_op.name, default_type) \
                     if isinstance(dst_op, RegisterOperand) else ctx.vreg(default_type)
            builder.emit(IRInstr(op=ir_op, dst=dst, srcs=[], lineno=lineno))
            return

        self.errors.append(f"Cannot lower opcode '{op}' with {len(ops)} operands at line {lineno}")

    # -----------------------------------------------------------------------
    # Data section — produces global IRInstrs
    # -----------------------------------------------------------------------

    def _lower_data_section(self, section: Section, module: IRModule):
        for stmt in section.body:
            if isinstance(stmt, Directive):
                type_map = {
                    '.byte':   IRType.U8,
                    '.word':   IRType.U16,
                    '.long':   IRType.U32,
                    '.quad':   IRType.U64,
                }
                if stmt.name in type_map:
                    t = type_map[stmt.name]
                    for arg in stmt.args:
                        try:
                            val = int(arg, 0)
                            module.globals.append(IRInstr(
                                op=IROp.STORE,
                                srcs=[Immediate(val, t)],
                                lineno=stmt.lineno,
                            ))
                        except ValueError:
                            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lower(program: Program) -> IRModule:
    lowerer = IRLowerer()
    module  = lowerer.lower(program)
    if lowerer.errors:
        for e in lowerer.errors:
            print(f"[IR Lower] {e}")
    return module
