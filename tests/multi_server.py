#!/usr/bin/env python3
# tests/multi_server.py

"""
Test server demonstrating terminaide multi-script routing.

This server serves multiple terminal applications through a browser-based interface:
- Root path ("/") provides access to the demo application
- "/quotes" serves the quote guessing game
- "/snake" serves the ASCII snake game

Each route runs its own dedicated ttyd process, demonstrating the new multi-script
routing capability of terminaide.
"""

import logging
import os
from pathlib import Path
from fastapi import FastAPI
from terminaide import serve_tty

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:     %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(title="Terminaide Multi-Script Demo")

# Get the current directory for script paths
current_dir = Path(__file__).parent

# Configure the terminal service with multiple script routes
serve_tty(
    app,
    # For the multi-script setup, we need to explicitly set client_script
    # This will be used for the root path
    client_script=Path(__file__).parent.parent / "terminaide" / "demos" / "instructions.py",
    script_routes={
        "/quotes": current_dir / "client_1.py",  # Quote guessing game
        "/snake": current_dir / "client_2.py",  # ASCII snake game
    },
    mount_path="/",
    theme={
        # "background": "#1e1e1e",  # Dark background
        # "foreground": "#f0f0f0",  # Light text
        "cursor": "#ffa500",      # Orange cursor
    },
    ttyd_options={
        "check_origin": False,
        "max_clients": 5,         # Allow multiple clients per terminal
    },
    debug=True,
)

# Add a simple route to explain available terminals
@app.get("/info")
async def info():
    """Provide information about available terminal applications."""
    return {
        "message": "Terminaide Multi-Script Demo",
        "available_terminals": [
            {
                "path": "/",
                "description": "Built-in demo that explains terminaide",
            },
            {
                "path": "/quotes",
                "description": "Quote guessing game - guess the author of famous quotes",
            },
            {
                "path": "/snake",
                "description": "ASCII snake game - use WASD keys to move",
            }
        ],
        "usage": "Visit these paths in your browser to access different terminal applications."
    }

# Start the server when running this file directly
if __name__ == '__main__':
    import uvicorn
    
    # Get port from environment or use default
    server_port = int(os.environ.get('PORT', '8000'))
    
    uvicorn_config = {
        "app": "multi_server:app",
        "host": "0.0.0.0",
        "port": server_port,
        "log_level": "info",
        "reload": True,
        "reload_dirs": ["./"]
    }

    logger.info(f"Starting multi-script server on port {server_port}")
    logger.info("Available routes:")
    logger.info("  / - Built-in demo")
    logger.info("  /quotes - Quote guessing game")
    logger.info("  /snake - ASCII snake game")
    logger.info("  /info - Server information")
    
    uvicorn.run(**uvicorn_config)