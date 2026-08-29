#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nexus.builtins import make_builtins
from nexus.compiler import compile_program
from nexus.errors import NexusError
from nexus.interpreter import Interpreter
from nexus.lexer import Lexer
from nexus.parser import Parser
from nexus.vm import VM


def run_source(source: str, engine: str = "vm") -> int:
    try:
        tokens = Lexer(source).tokenize()
        statements = Parser(tokens).parse()
        if engine == "vm":
            proto = compile_program(statements)
            VM(make_builtins()).run_program(proto)
        else:
            Interpreter(make_builtins()).run(statements)
        return 0
    except NexusError as e:
        print(f"Error: {e.message}" + (f" (line {e.line})" if e.line else ""), file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Run a Nexus script")
    parser.add_argument("script", help="Path to a .nx script")
    parser.add_argument(
        "--engine", choices=["vm", "tree"], default="vm",
        help="Execution engine: 'vm' (bytecode VM, default) or 'tree' (tree-walking interpreter)",
    )
    args = parser.parse_args()

    path = Path(args.script)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    source = path.read_text()
    sys.exit(run_source(source, engine=args.engine))


if __name__ == "__main__":
    main()
