#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nexus.builtins import make_builtins
from nexus.compiler import compile_program
from nexus.errors import NexusError
from nexus.interpreter import Interpreter
from nexus.jsgen import generate_js
from nexus.lexer import Lexer
from nexus.native import NativeCompileError, compile_native
from nexus.parser import Parser
from nexus.typechecker import check_types
from nexus.vm import VM


def run_source(source: str, engine: str = "vm", typecheck: bool = True, native: bool = False) -> int:
    try:
        tokens = Lexer(source).tokenize()
        statements = Parser(tokens).parse()
        if typecheck:
            check_types(statements)

        wrappers = {}
        if native:
            try:
                wrappers, compiled, skipped = compile_native(statements)
                print(f"[native] compiled: {', '.join(compiled)}", file=sys.stderr)
                for name, reason in skipped.items():
                    print(f"[native] skipped '{name}': {reason}", file=sys.stderr)
            except NativeCompileError as e:
                print(f"[native] {e.message}", file=sys.stderr)

        if engine == "vm":
            proto = compile_program(statements)
            VM(make_builtins(), native=wrappers).run_program(proto)
        else:
            Interpreter(make_builtins(), native=wrappers).run(statements)
        return 0
    except NexusError as e:
        print(f"Error: {e.message}" + (f" (line {e.line})" if e.line else ""), file=sys.stderr)
        return 1


def transpile_to_js(source: str, out_path: Path) -> int:
    try:
        tokens = Lexer(source).tokenize()
        statements = Parser(tokens).parse()
        check_types(statements)
        js_source = generate_js(statements)
    except NexusError as e:
        print(f"Error: {e.message}" + (f" (line {e.line})" if e.line else ""), file=sys.stderr)
        return 1
    out_path.write_text(js_source)
    print(f"Wrote {out_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run or transpile a Nexus script")
    parser.add_argument("script", help="Path to a .nx script")
    parser.add_argument(
        "--engine", choices=["vm", "tree"], default="vm",
        help="Execution engine: 'vm' (bytecode VM, default) or 'tree' (tree-walking interpreter)",
    )
    parser.add_argument(
        "--no-typecheck", action="store_true",
        help="Skip the static type checker (only annotated code is ever checked)",
    )
    parser.add_argument(
        "--native", action="store_true",
        help="AOT-compile eligible number-only top-level functions to native code via gcc",
    )
    parser.add_argument(
        "--target", choices=["run", "js"], default="run",
        help="'run' executes the script (default); 'js' transpiles it to a .js file instead",
    )
    args = parser.parse_args()

    path = Path(args.script)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    source = path.read_text()

    if args.target == "js":
        sys.exit(transpile_to_js(source, path.with_suffix(".js")))

    sys.exit(run_source(source, engine=args.engine, typecheck=not args.no_typecheck, native=args.native))


if __name__ == "__main__":
    main()
