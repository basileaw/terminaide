# server.py

"""
Test server for terminaide that demonstrates all API modes.
Usage:
python demo/server.py                     # Default mode - shows getting started interface
python demo/server.py function            # Function mode - demo of serve_function() with Asteroids
python demo/server.py script              # Script mode - demo of serve_script()
python demo/server.py apps                # Apps mode - HTML page at root, terminal games at routes
python demo/server.py container           # Run the apps mode in a Docker container
"""

import os
import uvicorn
import argparse
from fastapi import FastAPI
from terminaide import logger
from terminaide import serve_function, serve_script, serve_apps
from terminaide import HtmlIndex
from terminaide.terminarcade import (
    play_snake,
    play_tetris,
    play_pong,
    play_asteroids,
    instructions,
)
from demo.container import build_and_run_container


def create_index_page() -> HtmlIndex:
    """Create HtmlIndex configuration for the terminal arcade."""
    return HtmlIndex(
        title="TERMIN-ARCADE",
        subtitle="This demo shows HTML pages and terminal applications combined in one server, running a separate terminal for each game.",
        menu=[
            {
                "label": "Available Games",
                "options": [
                    {"path": "/snake", "title": "Snake"},
                    {"path": "/tetris", "title": "Tetris"},
                    {"path": "/pong", "title": "Pong"},
                    {"path": "/asteroids", "title": "Asteroids"},
                ],
            }
        ],
    )


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


app = None


def create_app() -> FastAPI:
    """Create the FastAPI app for apps mode."""
    global app
    app = FastAPI(title="Terminaide - APPS Mode")
    serve_apps(
        app,
        terminal_routes={
            "/": create_index_page(),
            "/snake": {
                "function": play_snake,
                "title": "Snake",
            },
            "/tetris": {
                "function": play_tetris,
                "title": "Tetris",
            },
            "/pong": {
                "function": play_pong,
                "title": "Pong",
            },
            "/asteroids": {
                "function": play_asteroids,
                "title": "Asteroids",
            },
        },
        debug=True,
    )
    return app


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
        logger.setLevel(log_level)
        import logging

        logging.getLogger("uvicorn").setLevel(log_level)

    if mode == "container":
        build_and_run_container(port)
        return

    # DEFAULT MODE
    if mode == "default":
        serve_function(
            instructions,
            port=port,
            title="Instructions",
            debug=True,
            reload=True,
        )
        return

    # FUNCTION MODE
    if mode == "function":
        serve_function(
            play_asteroids,
            port=port,
            title="Function Mode",
            debug=True,
        )
        return

    # SCRIPT MODE
    if mode == "script":
        serve_script(
            "demo/client.py",
            port=port,
            title="Script Mode",
            debug=True,
        )
        return

    # APPS MODE
    if mode == "apps":
        create_app()
        uvicorn.run(
            "demo.server:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            reload_dirs=["."],
        )


# When uvicorn imports this module in reload mode, check if we need to create the app
if os.environ.get("TERMINAIDE_MODE") == "apps" and app is None:
    create_app()

if __name__ == "__main__":
    main()
