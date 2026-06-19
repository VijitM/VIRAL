import streamlit as st

st.set_page_config(page_title="VIRAL", layout="wide")

import sys
import traceback

# Import backend modules
# Assuming the existing backend files are in the same directory.
try:
    import parser
    import ir_lower
    from backend_x86 import X86Backend
    from backend_arm64 import ARM64Backend
    from backend_riscv import RISCVBackend
except ImportError as e:
    st.error(f"Error importing backend modules: {e}")
    st.info("Make sure `parser.py`, `ir_lower.py`, and the `backend_*.py` files are in the same directory.")

def compile_code(source_text: str, target_arch: str) -> str:
    """Mock version of the compiler pipeline wrapping the actual backend."""
    # 1. Parse into AST
    ast = parser.parse(source_text)
    
    # 2. Lower AST to IR
    ir_module = ir_lower.lower(ast)
    if not ir_module:
        raise ValueError("IR Lowering failed to produce a module.")
        
    # 3. Instantiate correct backend
    if target_arch == "x86-64":
        backend = X86Backend()
    elif target_arch == "ARM64":
        backend = ARM64Backend()
    elif target_arch == "RISC-V":
        backend = RISCVBackend()
    else:
        raise ValueError(f"Unknown target architecture: {target_arch}")
        
    # 4. Emit target assembly
    asm_text = backend.emit_module(ir_module)
    return asm_text

# ----------------- UI Layout & Configuration -------

# Header
st.title("VIRAL")
st.markdown("A web interface for the custom, pure-Python compiler/assembler. Converts a portable typed assembly language into target-specific machine code (x86-64, ARM64, and RISC-V).")

DEMO_CODE = """\
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

# Initialize session state for the editor
if "source_code" not in st.session_state:
    st.session_state["source_code"] = ""

def load_demo():
    st.session_state["source_code"] = DEMO_CODE

# Middle control section
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    target_arch = st.radio("Target Architecture", options=["x86-64", "ARM64", "RISC-V"])

with col2:
    st.write("") # Spacing
    st.write("")
    compile_clicked = st.button("🚀 Compile", type="primary", use_container_width=True)

# Main layout: Left for Input, Right for Output
left_col, right_col = st.columns(2)

with left_col:
    st.subheader("Source Code (Portable Assembly)")
    
    # Top bar for input controls
    btn_col, upload_col = st.columns([1, 2])
    with btn_col:
        st.button("Load Demo", on_click=load_demo)
    with upload_col:
        uploaded_file = st.file_uploader("Upload .s or .txt", type=["s", "txt"], label_visibility="collapsed")
        if uploaded_file is not None:
            # Decode and set to session state if it changed
            content = uploaded_file.getvalue().decode("utf-8")
            if content != st.session_state.get("uploaded_content"):
                st.session_state["source_code"] = content
                st.session_state["uploaded_content"] = content
                st.rerun()

    # Text editor
    source_text = st.text_area(
        "Editor",
        value=st.session_state["source_code"],
        height=500,
        label_visibility="collapsed"
    )

with right_col:
    st.subheader("Compiled Target Assembly")
    
    if compile_clicked:
        if not source_text.strip():
            st.warning("Please enter some source code to compile.")
        else:
            try:
                # Call compiler pipeline
                result = compile_code(source_text, target_arch)
                # Display output
                st.code(result, language="x86asm" if "x86" in target_arch else "assembly", wrap_lines=True)
                st.success("Compilation successful!")
            except Exception as e:
                # Output error console
                st.error("Compilation Error")
                st.code(traceback.format_exc(), language="python")
    else:
        st.info("Click 'Compile' to generate assembly.")
