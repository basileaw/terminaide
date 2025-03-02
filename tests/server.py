# tests/server.py

"""
Test server demonstrating terminaide integration with root mounting.
This server serves a quote guessing game through a browser-based terminal.
"""

import logging
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
app = FastAPI()

# Set up the terminal service at the root path
client_script = Path(__file__).parent / "client.py"

# Configure the terminal service
serve_tty(
    app,
    # client_script=client_script,
    mount_path="/",
    theme={
        "background": "black",
    },
    ttyd_options={
        "check_origin": False,
        "max_clients": 1,
    },
    debug=True,
    title="Terminaide"
)

# Start the server when running this file directly
if __name__ == '__main__':
    import uvicorn
    
    server_port = int('8000')
    
    uvicorn_config = {
        "app": "server:app",
        "host": "0.0.0.0",
        "port": server_port,
        "log_level": "info",
        "reload": True,
        "reload_dirs": ["./"]
    }

    logger.info(f"Starting server on port {server_port}")
    
    uvicorn.run(**uvicorn_config)