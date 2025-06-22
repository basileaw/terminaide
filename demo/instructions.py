#!/usr/bin/env python3
"""
Default demo showing terminaide instructions.

This is the entry point when running `make serve` without arguments.

Usage:
    python demo/instructions.py
"""

from terminaide import serve_function
from terminarcade import instructions

if __name__ == "__main__":
    serve_function(
        instructions,
        port=8000,
        title="Instructions",
    )