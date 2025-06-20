# terminaide/__init__.py

"""
terminaide: Serve Python CLI applications in the browser using ttyd.

This package provides tools to easily serve Python CLI applications through
a browser-based terminal using ttyd. It handles binary installation and
management automatically across supported platforms.

Public API:
- serve_function(): Serve a Python function in a browser terminal
- serve_script(): Serve a Python script file in a terminal  
- serve_apps(): Integrate multiple terminals into a FastAPI application
- AutoIndex: Create navigable index pages (HTML or Curses)
- termin_ascii(): Generate ASCII banners
- Monitor: Process output monitoring with rich terminal interface

Supported Platforms:
- Linux x86_64 (Docker containers)
- macOS ARM64 (Apple Silicon)
"""

import logging

# Import complete public API from single source of truth
from .termin_api import *

# Get package-level logger (configuration happens when serve_* functions are called)
logger = logging.getLogger("terminaide")
