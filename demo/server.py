# server.py

"""
Test server for terminaide that demonstrates all three API tiers.
Usage:
python demo/server.py                     # Default mode - shows getting started interface
python demo/server.py --function          # Function mode - demo of serve_function() with Asteroids
python demo/server.py --script            # Script mode - demo of serve_script()
python demo/server.py --apps              # Apps mode - HTML page at root, terminal games at routes
python demo/server.py --container         # Run the apps mode in a Docker container
"""

import os
import sys
import json
import uvicorn
import argparse
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# Add project root to path to ensure imports work correctly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from terminaide import logger
from terminaide import serve_function, serve_script, serve_apps, termin_ascii
from terminaide.core.index_page import IndexPage
from demo.container import build_and_run_container

CURRENT_DIR = Path(__file__).parent
CLIENT_SCRIPT = CURRENT_DIR / "client.py"
# Convert project_root to a Path object for path operations
project_root_path = Path(project_root)
INSTRUCTIONS_PATH = (
    project_root_path / "terminaide" / "terminarcade" / "instructions.py"
)

MODE_HELP = {
    "default": "Default (getting started interface)",
    "function": "Serve function mode (Asteroids)",
    "script": "Serve script mode",
    "apps": "Apps mode (HTML + routes)",
    "container": "Docker container mode (same as apps)",
}


def create_index_page() -> IndexPage:
    """Create IndexPage configuration for the terminal arcade."""
    return IndexPage(
        title="TERMIN-ARCADE",
        subtitle="This demo shows how HTML pages and terminal applications can be combined in one server. Each game runs in its own terminal instance.",
        menu=[
            {
                "label": "Available Games",
                "options": [
                    {"path": "/snake", "title": "Snake"},
                    {"path": "/tetris", "title": "Tetris"},
                    {"path": "/pong", "title": "Pong"},
                    {"path": "/info", "title": "Server Info"},
                ],
            }
        ],
    )


def create_info_endpoint(app: FastAPI, mode: str, description: str) -> None:
    @app.get("/info", response_class=HTMLResponse)
    async def info(request: Request) -> HTMLResponse:
        info_dict = {
            "mode": mode,
            "description": description,
            "client_script": str(CLIENT_SCRIPT),
            "modes": MODE_HELP,
            "usage": "python demo/server.py [--default|--function|--script|--apps|--container]",
            "notes": [
                "serve_function: Simplest - just pass a function",
                "serve_script: Simple - pass a script file",
                "serve_apps: Advanced - integrate with FastAPI",
            ],
        }
        html_content = f"""<!DOCTYPE html>
        <html>
        <head>
            <title>Terminaide Info</title>
            <link rel="icon" type="image/x-icon" href="/terminaide-static/favicon.ico">
        </head>
        <body><pre>{json.dumps(info_dict, indent=2)}</pre></body>
        </html>"""
        return HTMLResponse(content=html_content)


def play_asteroids_function() -> None:
    from terminaide.terminarcade import play_asteroids

    play_asteroids()


def create_app() -> FastAPI:
    """
    Factory function: read mode from environment, build and return FastAPI app.
    Used by Uvicorn with 'factory=True' so it can reload properly.
    """
    mode = os.environ.get("TERMINAIDE_MODE", "default")
    app = FastAPI(title=f"Terminaide - {mode.upper()} Mode")
    description = ""

    # Don't try to use any Docker stuff here - just handle the apps mode
    if mode == "apps":
        description = "Apps mode - HTML root + separate terminal routes"
        serve_apps(
            app,
            terminal_routes={
                "/": create_index_page(),
                "/snake": {
                    "client_script": [CLIENT_SCRIPT, "--snake"],
                    "title": "Termin-Arcade (Snake)",
                },
                "/tetris": {
                    "client_script": [CLIENT_SCRIPT, "--tetris"],
                    "title": "Termin-Arcade (Tetris)",
                },
                "/pong": {
                    "client_script": [CLIENT_SCRIPT, "--pong"],
                    "title": "Termin-Arcade (Pong)",
                },
            },
            debug=True,
        )
        create_info_endpoint(app, mode, description)

    return app


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

    # Store the mode directly
    args.actual_mode = args.mode
    return args


def main() -> None:
    args = parse_args()
    mode = args.actual_mode
    port = args.port
    os.environ["TERMINAIDE_MODE"] = mode

    if mode != "container":
        os.environ["WATCHFILES_FORCE_POLLING"] = "0"
        os.environ["WATCHFILES_POLL_DELAY"] = "0.1"
        os.environ["TERMINAIDE_VERBOSE"] = "0"
        log_level = "WARNING" if mode != "apps" else "INFO"
        # Set terminaide logger level directly
        logger.setLevel(log_level)
        # Also set uvicorn logger level
        import logging

        logging.getLogger("uvicorn").setLevel(log_level)

    logger.info(f"Starting server in {mode.upper()} mode on port {port}")

    if mode == "container":
        build_and_run_container(port)
        return

    # DEFAULT MODE
    if mode == "default":
        serve_script(
            INSTRUCTIONS_PATH,
            port=port,
            title="Instructions",
            debug=True,
            reload=True,  # <-- Enable reload for default mode
        )
        return

    # FUNCTION MODE
    if mode == "function":
        serve_function(
            play_asteroids_function,
            port=port,
            title="Function Mode",
            debug=True,
            reload=True,  # <-- Enable reload for function mode
        )
        return

    # SCRIPT MODE
    if mode == "script":
        serve_script(
            CLIENT_SCRIPT,
            port=port,
            title="Script Mode",
            debug=True,
            reload=True,  # <-- Enable reload for script mode
        )
        return

    # APPS MODE
    if mode == "apps":
        uvicorn.run(
            "demo.server:create_app",
            factory=True,
            host="0.0.0.0",
            port=port,
            reload=True,
            reload_dirs=[str(project_root)],
        )


if __name__ == "__main__":
    main()
