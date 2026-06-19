# VIRAL — A Mini Compiler with Web Frontend

VIRAL is a compiler built from scratch in Python, implementing a full compilation pipeline — lexical analysis, parsing, type checking, intermediate representation (IR) generation, and native code generation — paired with a web-based interface for writing, compiling, and testing source code interactively.

## Features

- **Lexical Analysis** — Tokenizes source code (`lexer.py`)
- **Parsing** — Builds an AST using a PLY-based grammar (`parser.py`, with auto-generated `parsetab.py` / `parser.out`)
- **Type Checking** — Static semantic analysis and type validation (`typechecker.py`)
- **Intermediate Representation** — Custom IR with a lowering pass to target-independent instructions (`ir.py`, `ir_lower.py`)
- **Code Generation** — Native backend targeting:
  - **x86-64** (primary target) — includes register allocation and function-call support (`backend_x86.py`, `backend.py`, `asm_ast.py`)
  - **ARM64** (`backend_arm64.py`)
  - **RISC-V** (`backend_riscv.py`)
- **Web Interface** — Browser-based editor to write source code, trigger compilation, and view output (React + Vite + TypeScript)

## Architecture

```
Source Code
    │
    ▼
Lexer (lexer.py) ──► Tokens
    │
    ▼
Parser (parser.py) ──► AST
    │
    ▼
Type Checker (typechecker.py) ──► Validated AST
    │
    ▼
IR Generator (ir.py, ir_lower.py) ──► Lowered IR
    │
    ▼
Backend (backend_x86.py / backend_arm64.py / backend_riscv.py) ──► Native Assembly
```

## Project Structure

```
VIRAL/
├── lexer.py                 # Tokenizer
├── parser.py                 # Grammar & AST construction (PLY)
├── parsetab.py / parser.out  # Auto-generated parser tables (PLY output)
├── typechecker.py            # Type checking / semantic analysis
├── ir.py                     # Intermediate representation
├── ir_lower.py                # IR lowering pass
├── asm_ast.py                  # Assembly-level AST
├── backend.py                  # Shared backend logic
├── backend_x86.py              # x86-64 codegen, register allocation, function calls
├── backend_arm64.py            # ARM64 codegen
├── backend_riscv.py            # RISC-V codegen
├── main.py                     # Compiler entry point / driver
│
├── src/                        # Frontend (React + TypeScript)
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── .env.example
```

## Getting Started

### Backend (Compiler)

**Prerequisites:** Python 3.x, [PLY](https://pypi.org/project/ply/)

```bash
pip install ply
python main.py <path-to-source-file>
```
> Update the run command above if `main.py` expects different arguments.

### Frontend (Web Interface)

**Prerequisites:** Node.js

```bash
npm install
npm run dev
```
If the app uses an external API key (see `.env.example`), copy it to `.env.local` and fill in the value before running.

## Contributors

| Contributor | Contributions |
|---|---|
| **Vijit Mehrotra** ([@VijitM](https://github.com/VijitM)) | Core compiler pipeline — lexer, parser, type checker, IR, backend architecture |
| **Unnati** | x86-64 register allocation, function-call support, web frontend & testing interface |

*(Update this table to credit all team members accurately.)*

## License

No license file is currently included. Add one (e.g. MIT) if you plan to share or open-source this project.
