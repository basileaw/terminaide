#!/usr/bin/env python3
# tests/server.py

"""
Test server for terminaide that supports multiple configuration permutations.

This script allows testing different ways of configuring terminaide to understand
how each permutation behaves, particularly regarding root path handling.

Usage:
    python server.py --mode single
    python server.py --mode demo
    python server.py --mode multi_no_root
    python server.py --mode multi_with_root
    python server.py --mode combined
    python server.py --mode user_root_after
    python server.py --mode user_root_before
"""

import argparse
import logging
import os
import sys
import json  # <-- Added
from pathlib import Path
from typing import Dict, Optional, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from terminaide import serve_tty

import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:     %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get the current directory
CURRENT_DIR = Path(__file__).parent
CLIENT_SCRIPT = CURRENT_DIR / "client.py"


def create_custom_root_endpoint(app: FastAPI):
    """Add a custom root endpoint to the app that returns HTML."""
    @app.get("/", response_class=HTMLResponse)
    async def custom_root(request: Request):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Terminaide</title>
            <link rel="icon" type="image/x-icon" href="{request.url_for('static', path='favicon.ico')}">
            <style>
                body {{
                    font-family: 'Courier New', monospace;
                    line-height: 1.5;
                    color: #f0f0f0;
                    background-color: black;
                    text-align: center;
                    padding: 40px 20px;
                    margin: 0;
                }}
                h1 {{
                    color: #3498db;
                    border-bottom: 1px solid #3498db;
                    padding-bottom: 15px;
                    margin: 0 auto 30px;
                    max-width: 600px;
                }}
                .card {{
                    background-color: #2d2d2d;
                    max-width: 600px;
                    margin: 0 auto 30px;
                    padding: 20px;
                }}
                .terminal-box {{
                    border: 1px solid #3498db;
                    max-width: 400px;
                    margin: 30px auto;
                    padding: 10px;
                }}
                .links {{
                    display: flex;
                    justify-content: center;
                    gap: 20px;
                    margin: 30px auto;
                }}
                .terminal-link {{
                    display: inline-block;
                    background-color: #3498db;
                    color: #000;
                    padding: 8px 20px;
                    text-decoration: none;
                    font-weight: bold;
                }}
                .info-link {{
                    color: #3498db;
                    text-decoration: none;
                    margin-top: 40px;
                    display: inline-block;
                }}
            </style>
        </head>
        <body>
            <h1>Terminaide Terminal Games</h1>
            
            <div class="card">
                This demo shows how a single client script can run different games based on command-line arguments.
            </div>
            
            <div class="terminal-box">
                Available Terminal Games
            </div>
            
            <div class="links">
                <a href="/terminal1" class="terminal-link">Snake Game</a>
                <a href="/terminal2" class="terminal-link">Pong Game</a>
            </div>
            
            <a href="/info" class="info-link">Server Configuration Info</a>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)


def create_info_endpoint(app: FastAPI, mode: str, description: str):
    """Add an info endpoint that explains the current configuration."""
    @app.get("/info", response_class=HTMLResponse)  # <-- Changed to HTMLResponse
    async def info(request: Request):
        info_dict = {
            "mode": mode,
            "description": description,
            "client_script": str(CLIENT_SCRIPT),
            "permutations": {
                "single": "Single script basic usage - client.py runs at root",
                "demo": "No script specified - demo runs at root",
                "multi_no_root": "Multiple scripts without root - demo at root, other scripts at paths",
                "multi_with_root": "Multiple scripts with root - client.py at root, other paths defined",
                "combined": "Combined approaches - explicit client_script and script_routes",
                "user_root_after": "User defines root AFTER terminaide - user route wins",
                "user_root_before": "User defines root BEFORE terminaide - user route wins"
            },
            "usage": "Change mode by running with --mode [mode_name]"
        }
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Terminaide Info</title>
    <link rel="icon" type="image/x-icon" href="{request.url_for('static', path='favicon.ico')}">
</head>
<body>
    <pre>{json.dumps(info_dict, indent=2)}</pre>
</body>
</html>"""


def create_app() -> FastAPI:
    """
    Factory function that Uvicorn will import and call on each reload.

    Reads the mode from the environment instead of a global variable so that
    watchfiles reload can re-import this factory.
    """
    mode = os.environ.get("TERMINAIDE_MODE", "demo")
    app = FastAPI(title=f"Terminaide Test - {mode.upper()} Mode")

    # We declare a local variable to describe the current configuration
    description = ""

    # First add HTML root endpoint for all modes except when root is explicitly handled
    if mode not in ["single", "multi_with_root", "combined"]:
        # Define HTML root endpoint BEFORE serve_tty (except for user_root_after)
        if mode != "user_root_after":
            create_custom_root_endpoint(app)

    # Mode-specific configuration
    if mode == "single":
        description = "Single script at root path - client.py runs at /"
        serve_tty(
            app,
            client_script=CLIENT_SCRIPT,
            title="Single Script Mode",
            debug=True
        )
        
    elif mode == "demo":
        description = "HTML page at root path, no script specified"
        serve_tty(
            app,
            title="Demo Mode with HTML Root",
            debug=True
        )
        
    elif mode == "multi_no_root":
        description = "HTML page at root, scripts with different game demos at other paths"
        serve_tty(
            app,
            script_routes={
                "/terminal1": [CLIENT_SCRIPT, "--snake"],  # Snake game
                "/terminal2": [CLIENT_SCRIPT, "--pong"]    # Pong game
            },
            title="Multi-Script With HTML Root",
            debug=True
        )
        
    elif mode == "multi_with_root":
        description = "Multiple scripts with root - client.py at /, others at different game demos"
        serve_tty(
            app,
            script_routes={
                "/": CLIENT_SCRIPT,                        # Instructions
                "/terminal1": [CLIENT_SCRIPT, "--snake"],  # Snake game
                "/terminal2": [CLIENT_SCRIPT, "--pong"]    # Pong game
            },
            title="Multi-Script With Root",
            debug=True
        )
        
    elif mode == "combined":
        description = "Combined approaches - client_script (index) at root, other routes with games"
        serve_tty(
            app,
            client_script=[CLIENT_SCRIPT, "--index"],      # Index menu at root
            script_routes={
                "/terminal1": [CLIENT_SCRIPT, "--snake"],  # Snake game
                "/terminal2": [CLIENT_SCRIPT, "--pong"]    # Pong game
            },
            title="Combined Approach",
            debug=True
        )
        
    elif mode == "user_root_after":
        description = "User defines root AFTER terminaide - user route wins"
        serve_tty(
            app,
            script_routes={
                "/terminal1": [CLIENT_SCRIPT, "--snake"],  # Snake game
                "/terminal2": [CLIENT_SCRIPT, "--pong"]    # Pong game
            },
            title="User Root After",
            debug=True
        )
        # Define custom root AFTER serve_tty
        create_custom_root_endpoint(app)
        
    elif mode == "user_root_before":
        description = "User defines root BEFORE terminaide - user route wins"
        create_custom_root_endpoint(app)
        serve_tty(
            app,
            script_routes={
                "/terminal1": [CLIENT_SCRIPT, "--snake"],  # Snake game
                "/terminal2": [CLIENT_SCRIPT, "--pong"]    # Pong game
            },
            title="User Root Before",
            debug=True
        )
        
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Add info endpoint
    create_info_endpoint(app, mode, description)

    return app


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Test server for terminaide with different configuration permutations."
    )
    parser.add_argument(
        "--mode",
        choices=["single", "demo", "multi_no_root", "multi_with_root",
                 "combined", "user_root_after", "user_root_before"],
        default="demo",
        help="Which configuration permutation to test (default: demo)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000)"
    )
    return parser.parse_args()


def main():
    """
    Main function to run the server with watchfiles reload.
    We store --mode in an environment variable so create_app() can read it
    after re-importing this module on each reload.
    """
    args = parse_args()

    # Set mode in an env variable so create_app() sees it on reload
    os.environ["TERMINAIDE_MODE"] = args.mode

    logger.info(f"Starting server in {args.mode.upper()} mode on port {args.port}")
    logger.info(f"Visit http://localhost:{args.port} to see the main interface")
    logger.info(f"Visit http://localhost:{args.port}/info for configuration details")

    if args.mode not in ["single", "demo"]:
        logger.info("Available terminal routes:")
        if args.mode not in ["user_root_after", "user_root_before"]:
            if args.mode == "multi_with_root":
                logger.info("  / - Terminal running client.py (Instructions)")
            elif args.mode == "combined":
                logger.info("  / - Terminal running client.py --index (Demo Index)")
            else:
                logger.info("  / - Custom HTML page")
        logger.info("  /terminal1 - Terminal running client.py --snake (Snake Game)")
        logger.info("  /terminal2 - Terminal running client.py --pong (Pong Game)")

    uvicorn.run(
        "tests.server:create_app",
        factory=True,
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        reload=True,
        reload_dirs=[str(CURRENT_DIR.parent)]
    )


if __name__ == '__main__':
    main()
