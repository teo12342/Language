#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nexus.builtins import make_builtins
from nexus.errors import NexusError
from nexus.interpreter import Interpreter
from nexus.lexer import Lexer
from nexus.parser import Parser


def run_source(source: str) -> int:
    try:
        tokens = Lexer(source).tokenize()
        statements = Parser(tokens).parse()
        Interpreter(make_builtins()).run(statements)
        return 0
    except NexusError as e:
        print(f"Error: {e.message}" + (f" (line {e.line})" if e.line else ""), file=sys.stderr)
        return 1


def main():
    if len(sys.argv) != 2:
        print("Usage: python cli.py <script.nx>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    source = path.read_text()
    sys.exit(run_source(source))


if __name__ == "__main__":
    main()
