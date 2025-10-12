#!/usr/bin/env python3
"""
Standalone example of terminaide's serve_apps() API.

This example shows how to integrate multiple terminal applications into a
single FastAPI server with HTML pages and terminal games at different routes.

Usage:
    python examples/apps.py
"""

import uvicorn
from fastapi import FastAPI
from terminaide import serve_apps, AutoIndex, ServerMonitor
from terminarcade import snake, tetris, pong, asteroids

# Create monitor instance
monitor = ServerMonitor(title="Termin-Arcade")


def create_index_page() -> AutoIndex:
    """Create AutoIndex configuration for the terminal arcade."""
    return AutoIndex(
        type="html",
        title="TERMIN-ARCADE",
        subtitle="This demo shows HTML pages and terminal applications combined in one server, running a separate terminal for each game.",
        menu=[
            {"path": "/snake", "title": "Snake"},
            {"path": "/tetris", "title": "Tetris"},
            {"path": "/pong", "title": "Pong"},
            {"path": "/asteroids", "title": "Asteroids"},
        ],
        instructions="Available Games",
        epititle="Server Monitor:\nhttp://localhost:8000/monitor",
    )


def create_app() -> FastAPI:
    """Create the FastAPI app with terminal routes."""
    app = FastAPI(title="Terminaide - APPS Mode Demo")

    serve_apps(
        app,
        banner=True,
        terminal_routes={
            "/": create_index_page(),
            "/monitor": {
                "function": ServerMonitor.read,
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
    uvicorn.run(
        "examples.apps:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["."],
    )
