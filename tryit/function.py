#!/usr/bin/env python3
"""
Standalone demo of terminaide's serve_function() API.

This example shows how to serve a Python function directly in the terminal.
The function (asteroids game) will run in a web-based terminal interface.

Usage:
    python tryit/function.py
"""

from terminaide import serve_function
from terminarcade import asteroids

if __name__ == "__main__":
    serve_function(asteroids, title="Asteroids Game")
