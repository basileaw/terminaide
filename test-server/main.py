# test-server/main.py

"""
Test server demonstrating protottyde integration with root mounting.
This server serves a quote guessing game through a browser-based terminal.
"""

import os
import logging
from pathlib import Path
from fastapi import FastAPI
from protottyde import serve_tty

# Configure logging to see detailed information about what's happening
# This is particularly useful during development and debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:     %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Initialize our FastAPI application
# We don't need to add any CORS middleware or other handlers
# because protottyde will handle all the routing for us
app = FastAPI(
    title="Quote Guessing Game",
    description="A terminal-based game served through protottyde"
)

# Determine if we're running in a container environment
# This affects our configuration choices for development vs production
is_container = os.getenv('IS_CONTAINER', 'false').lower() == 'true'

# Configure our ports
# The server_port is what the FastAPI server listens on
# The ttyd_port is what the terminal process uses internally
server_port = int(os.getenv('PORT', '80' if is_container else '8000'))
ttyd_port = int(os.getenv('TTYD_PORT', '7681'))

# Set up the terminal service at the root path
# This creates a clean, professional experience where users see the terminal
# immediately upon visiting the site
client_script = Path(__file__).parent / "client" / "main.py"

# Configure the terminal service with our desired settings
serve_tty(
    app,
    client_script=client_script,
    mount_path="/",              # Mount at root for a clean URL
    port=ttyd_port,             # Use our configured ttyd port
    theme={                      # Configure the terminal appearance
        "background": "black",   # Black background for traditional terminal look
        # "foreground": "white",   # White text for good contrast
        # "cursor": "white",       # White cursor to match the text
    },
    ttyd_options={              # Configure ttyd behavior
        "check_origin": False,   # Allow connections from any origin
        "max_clients": 1,        # Only allow one client at a time
    },
    debug=not is_container      # Enable debug mode in development
)

# Start the server when running this file directly
if __name__ == '__main__':
    import uvicorn
    
    # Configure uvicorn for our needs
    uvicorn_config = {
        "app": "main:app",           # Point to our FastAPI instance
        "host": "0.0.0.0",          # Listen on all available interfaces
        "port": server_port,         # Use our configured server port
        "log_level": "info",         # Show informative logging
        
        # In development (not in container):
        # - Enable auto-reload for quick iterations
        # - Watch the current directory for changes
        **({"reload": True, "reload_dirs": ["./"]} if not is_container else {})
    }

    logger.info(
        f"Starting server on port {server_port} "
        f"({'development' if not is_container else 'production'} mode)"
    )
    
    # Start the uvicorn server with our configuration
    uvicorn.run(**uvicorn_config)