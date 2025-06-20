#!/usr/bin/env python3
# server.py

"""
Main router for terminaide demos - demonstrates all API modes.

This server acts as the primary entry point for all demo modes, delegating
to specialized modules for each mode while maintaining backward compatibility
with existing make commands.

Usage:
    make serve                     # Default mode - shows getting started interface
    make serve function            # Function mode - demo of serve_function() with Asteroids
    make serve script              # Script mode - demo of serve_script()
    make serve apps                # Apps mode - HTML page at root, terminal games at routes
    make serve container           # Run the apps mode in a Docker container

Or directly:
    python demo/server.py                     # Default mode
    python demo/server.py function            # Function mode
    python demo/server.py script              # Script mode
    python demo/server.py apps                # Apps mode
    python demo/server.py container           # Container mode
"""

import os
import sys
import argparse
from terminaide import serve_function, serve_script
from terminarcade import instructions

# Add demo directory to path for imports
demo_dir = os.path.dirname(os.path.abspath(__file__))
if demo_dir not in sys.path:
    sys.path.insert(0, demo_dir)




def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # Add a single positional argument for mode
    parser.add_argument(
        "mode",
        nargs="?",
        default="default",
        choices=["default", "function", "script", "apps", "container"],
        help="Server mode to run",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    args.actual_mode = args.mode
    return args


def main() -> None:
    args = parse_args()
    mode = args.actual_mode
    port = args.port

    # DEFAULT MODE - serve instructions directly
    if mode == "default":
        serve_function(
            instructions,
            port=port,
            title="Instructions",
        )
        return

    # DELEGATE TO OTHER MODULES
    # Each module is self-contained and can run independently
    
    if mode == "function":
        # Import and run function demo directly (uses default port 8000)
        from terminarcade import asteroids
        serve_function(asteroids, port=port, title="Asteroids Game")
        return

    if mode == "script":
        # Delegate to script.py (renamed from client.py)
        serve_script(
            os.path.join(demo_dir, "script.py"),
            port=port,
            title="Script Mode - Terminal Arcade",
        )
        return

    if mode == "apps":
        # Import and run apps demo with proper reload support
        import uvicorn
        # Set port in environment so apps module can use it
        os.environ["TERMINAIDE_PORT"] = str(port)
        uvicorn.run(
            "demo.apps:app", 
            host="0.0.0.0", 
            port=port, 
            reload=True, 
            reload_dirs=["."]
        )
        return

    if mode == "container":
        # Import and run container demo directly with custom port
        sys.path.insert(0, demo_dir)
        from container import build_and_run_container
        build_and_run_container(port)
        return

if __name__ == "__main__":
    main()
