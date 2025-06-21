#!/usr/bin/env python3
"""
Standalone demo of terminaide's serve_apps() API.

This example shows how to integrate multiple terminal applications into a
single FastAPI server with HTML pages and terminal games at different routes.

Usage:
    python demo/apps.py
"""

import uvicorn
from fastapi import FastAPI
from terminaide import serve_apps, AutoIndex, Monitor
from terminarcade import snake, tetris, pong, asteroids

# Create monitor instance
monitor = Monitor(title="Termin-Arcade")


def create_index_page() -> AutoIndex:
    """Create AutoIndex configuration for the terminal arcade."""
    import os

    port = int(os.environ.get("TERMINAIDE_PORT", 8000))

    return AutoIndex(
        type="html",
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
        epititle=f"Server Logs:\nhttp://localhost:{port}/monitor",
    )


def create_app() -> FastAPI:
    """Create the FastAPI app with terminal routes."""
    app = FastAPI(title="Terminaide - APPS Mode Demo")

    serve_apps(
        app,
        banner=False,
        terminal_routes={
            "/": create_index_page(),
            "/monitor": {
                "function": Monitor.read,
                "title": "Server Monitor",
            },
            "/snake": {
                "function": snake,
                "title": "Snake",
            },
            "/tetris": {
                "function": tetris,
                "title": "Tetris",
            },
            "/pong": {
                "function": pong,
                "title": "Pong",
            },
            "/asteroids": {
                "function": asteroids,
                "title": "Asteroids",
            },
        },
        debug=True,
    )

    return app


# Create app at module level for uvicorn reloading
app = create_app()

if __name__ == "__main__":
    import os

    # Use port from environment if set (for server.py routing), otherwise default to 8000
    port = int(os.environ.get("TERMINAIDE_PORT", 8000))

    uvicorn.run(
        "demo.apps:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=["."],
    )
