#!/usr/bin/env python3

"""Test server demonstrating ASCII banner with title functionality."""

from terminaide import serve_apps, HtmlIndex
from fastapi import FastAPI
import uvicorn


def create_test_index() -> HtmlIndex:
    """Create test index with simple title."""
    return HtmlIndex(
        title="Alex Basile",
        subtitle="Simple approach - title gets converted to ASCII art",
        epititle="KISS principle: Keep It Simple, Stupid!",
        menu=[
            {
                "label": "Test Options",
                "options": [
                    {"path": "/test1", "title": "Test Option 1"},
                    {"path": "/test2", "title": "Test Option 2"},
                    {"path": "https://github.com", "title": "External Link"},
                ],
            }
        ],
    )


if __name__ == "__main__":
    app = FastAPI()
    serve_apps(
        app,
        {
            "/": create_test_index(),
        },
    )
    uvicorn.run(app, host="0.0.0.0", port=8001)
