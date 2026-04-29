"""
main.py — Full compiler pipeline driver

Pipeline
--------
  Source text
    → Lexer      (lexer.py)
    → Parser     (parser.py)      → Program AST
    → TypeChecker (typechecker.py) → diagnostics
    → IR Lowering (ir_lower.py)   → IRModule
    → Backend    (backend_*.py)   → target assembly text

Usage
-----
  python main.py source.pasm --target x86-64
  python main.py source.pasm --target arm64
  python main.py source.pasm --target riscv64
  python main.py --demo --target x86-64
  python main.py --demo --target all      # emit all three targets
"""

import sys
import argparse

from parser    import parse
from typechecker import type_check, TypeError_, SemanticError
from ir_lower  import lower
from backend_x86    import X86Backend
from backend_arm64  import ARM64Backend
from backend_riscv  import RISCVBackend


# ---------------------------------------------------------------------------
# Available backends
# ---------------------------------------------------------------------------

BACKENDS = {
    'x86-64':  X86Backend,
    'arm64':   ARM64Backend,
    'riscv64': RISCVBackend,
}

# ---------------------------------------------------------------------------
# Demo source
# ---------------------------------------------------------------------------

DEMO_SOURCE = """\
.section .text
.global main

; Compute sum = a + b, store it, then return it
main:
    mov   r0:i64, #10
    mov   r1:i64, #32
    add   r2:i64, r0:i64, r1:i64
    push  r2
    call  print_int
    pop   r2
    ret   r2
"""

DEMO_SOURCE_LOOP = """\
.section .text
.global countdown

; Count down from 5 to 0
countdown:
    mov   r0:i64, #5
loop_top:
    cmp   r1:i64, r0:i64, #0
    push  r0
    call  print_int
    pop   r0
    sub   r0:i64, r0:i64, #1
    jgt   loop_top
    ret
"""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def compile_source(
    source:  str,
    target:  str,
    verbose: bool = False,
    emit_ir: bool = False,
) -> bool:
    """
    Run the full pipeline.
    Returns True if successful (no errors).
    """
    banner = lambda s: print(f"\n{'─'*3} {s} {'─'*(50-len(s))}")

    # ---- Stage 1: Parse ----
    banner("Parsing")
    program = parse(source)
    if verbose:
        print("  AST:")
        for sec in program.sections:
            print(f"    Section: {sec.name}")
            for stmt in sec.body:
                print(f"      {stmt}")

    # ---- Stage 2: Type check ----
    banner("Type checking")
    diagnostics = type_check(program)
    errors   = [d for d in diagnostics if isinstance(d, (TypeError_, SemanticError))]
    warnings = []

    for d in diagnostics:
        print(f"  {d}")
    if not diagnostics:
        print("  No issues.")

    if errors:
        print(f"\n  {len(errors)} error(s) — stopping.")
        return False

    # ---- Stage 3: IR lowering ----
    banner("IR lowering")
    module = lower(program)

    if emit_ir or verbose:
        print(module)
    else:
        fn_count = len(module.functions)
        print(f"  Lowered {fn_count} function(s) to IR.")

    # ---- Stage 4: Code generation ----
    targets = list(BACKENDS.keys()) if target == 'all' else [target]

    for tgt in targets:
        if tgt not in BACKENDS:
            print(f"  Unknown target '{tgt}'. Available: {', '.join(BACKENDS)}")
            continue

        banner(f"Code generation — {tgt}")
        backend  = BACKENDS[tgt]()
        asm_text = backend.emit_module(module)
        print(asm_text)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Portable typed assembler — full pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Targets:
  x86-64    Intel/AMD 64-bit (NASM Intel syntax)
  arm64     AArch64 / Apple Silicon
  riscv64   RISC-V RV64GC

Examples:
  python main.py program.pasm --target x86-64
  python main.py --demo --target all
  python main.py --demo-loop --target riscv64 --ir
        """,
    )
    ap.add_argument('file',        nargs='?',     help="Source .pasm file")
    ap.add_argument('--target',    default='x86-64',
                    help="Target architecture (default: x86-64)")
    ap.add_argument('--demo',      action='store_true', help="Run basic demo")
    ap.add_argument('--demo-loop', action='store_true', help="Run loop demo")
    ap.add_argument('--verbose',   action='store_true', help="Print AST nodes")
    ap.add_argument('--ir',        action='store_true', help="Print IR before codegen")
    ap.add_argument('--stdin',     action='store_true', help="Read source from stdin")
    args = ap.parse_args()

    if args.demo:
        print("=== Source ===")
        print(DEMO_SOURCE)
        compile_source(DEMO_SOURCE, args.target, args.verbose, args.ir)

    elif args.demo_loop:
        print("=== Source (loop) ===")
        print(DEMO_SOURCE_LOOP)
        compile_source(DEMO_SOURCE_LOOP, args.target, args.verbose, args.ir)

    elif args.stdin:
        source = sys.stdin.read()
        compile_source(source, args.target, args.verbose, args.ir)

    elif args.file:
        with open(args.file) as f:
            source = f.read()
        compile_source(source, args.target, args.verbose, args.ir)

    else:
        ap.print_help()


if __name__ == '__main__':
    main()
