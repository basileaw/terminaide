#!/usr/bin/env python3
# tests/server.py

"""
Test server for terminaide that supports multiple configuration permutations.

This script demonstrates different ways of configuring terminaide, with special
focus on the multi-script routing feature and command-line arguments.

Usage via poe (recommended):
    poe serve                # Run in demo mode
    poe serve mode=single    # Run in single script mode
    poe serve mode=multi_no_root port=8080  # Run on custom port

Direct usage:
    python server.py --mode single --port 8000
"""

import argparse
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from terminaide import serve_tty

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:     %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Get the current directory
CURRENT_DIR = Path(__file__).parent
CLIENT_SCRIPT = CURRENT_DIR / "client.py"

# Global variables to store configuration from command line
CURRENT_MODE = "demo"
CURRENT_PORT = 8000

# Mode descriptions
MODE_DESCRIPTIONS = {
    "single": "Single script basic usage - client.py runs at root",
    "demo": "No script specified - demo runs at root",
    "multi_no_root": "Multiple scripts without root - demo at root, other scripts at paths",
    "multi_with_root": "Multiple scripts with root - client.py at root, other paths defined",
    "combined": "Combined approaches - explicit client_script and script_routes",
    "user_root_after": "User defines root AFTER terminaide - user route wins",
    "user_root_before": "User defines root BEFORE terminaide - user route wins"
}

def create_custom_root_endpoint(app: FastAPI):
    """Add a custom root endpoint to the app that returns HTML."""
    @app.get("/", response_class=HTMLResponse)
    async def custom_root():
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Terminaide Test Server</title>
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }
                h1 {
                    color: #2c3e50;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 10px;
                }
                .card {
                    background-color: #f9f9f9;
                    border-left: 4px solid #3498db;
                    padding: 15px;
                    margin-bottom: 20px;
                    border-radius: 0 4px 4px 0;
                }
                .terminal-link {
                    display: inline-block;
                    background-color: #3498db;
                    color: white;
                    padding: 10px 15px;
                    margin: 5px;
                    text-decoration: none;
                    border-radius: 4px;
                    font-weight: bold;
                }
                .terminal-link:hover {
                    background-color: #2980b9;
                }
                .info {
                    background-color: #e8f4f8;
                    padding: 10px;
                    border-radius: 4px;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <h1>Terminaide Test Server</h1>
            
            <div class="card">
                <h2>Custom User-Defined Root</h2>
                <p>This is a custom HTML page defined by the user. It demonstrates that user-defined routes take precedence over terminaide's routes, even for the root path.</p>
            </div>
            
            <h2>Available Terminal Routes</h2>
            <a href="/terminal1" class="terminal-link">Terminal 1</a>
            <a href="/terminal2" class="terminal-link">Terminal 2 (--alternate mode)</a>
            
            <div class="info">
                <p>Visit <a href="/info">/info</a> for more details about the current configuration.</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=200)

def create_info_endpoint(app: FastAPI, mode: str, description: str):
    """Add an info endpoint that explains the current configuration."""
    @app.get("/info")
    async def info():
        return {
            "mode": mode,
            "description": description,
            "client_script": str(CLIENT_SCRIPT),
            "permutations": MODE_DESCRIPTIONS,
            "usage": "Change mode using 'poe serve mode=[mode_name]'"
        }
        
def create_app(mode: str) -> FastAPI:
    """Create and configure a FastAPI app based on the specified mode."""
    
    app = FastAPI(title=f"Terminaide Test - {mode.upper()} Mode")
    
    # Mode-specific configuration
    if mode == "single":
        # 1. Single Script (Basic Usage)
        description = MODE_DESCRIPTIONS[mode]
        serve_tty(
            app,
            client_script=CLIENT_SCRIPT,
            title="Single Script Mode",
            debug=True
        )
        
    elif mode == "demo":
        # 2. No Script Specified (Demo Mode)
        description = MODE_DESCRIPTIONS[mode]
        serve_tty(
            app,
            title="Demo Mode",
            debug=True
        )
        
    elif mode == "multi_no_root":
        # 3. Multiple Scripts Without Root
        description = MODE_DESCRIPTIONS[mode]
        serve_tty(
            app,
            script_routes={
                "/terminal1": CLIENT_SCRIPT,  # Normal mode
                "/terminal2": [CLIENT_SCRIPT, "--alternate"]  # With --alternate flag
            },
            title="Multi-Script No Root",
            debug=True
        )
        
    elif mode == "multi_with_root":
        # 4. Multiple Scripts With Root
        description = MODE_DESCRIPTIONS[mode]
        serve_tty(
            app,
            script_routes={
                "/": CLIENT_SCRIPT,  # Normal mode at root
                "/terminal1": CLIENT_SCRIPT,  # Normal mode
                "/terminal2": [CLIENT_SCRIPT, "--alternate"]  # With --alternate flag
            },
            title="Multi-Script With Root",
            debug=True
        )
        
    elif mode == "combined":
        # 5. Combined Approaches
        description = MODE_DESCRIPTIONS[mode]
        serve_tty(
            app,
            client_script=CLIENT_SCRIPT,  # Normal mode at root
            script_routes={
                "/terminal1": CLIENT_SCRIPT,  # Normal mode
                "/terminal2": [CLIENT_SCRIPT, "--alternate"]  # With --alternate flag
            },
            title="Combined Approach",
            debug=True
        )
        
    elif mode == "user_root_after":
        # 6. Custom User Root After Terminaide
        description = MODE_DESCRIPTIONS[mode]
        serve_tty(
            app,
            script_routes={
                "/terminal1": CLIENT_SCRIPT,  # Normal mode
                "/terminal2": [CLIENT_SCRIPT, "--alternate"]  # With --alternate flag
            },
            title="User Root After",
            debug=True
        )
        # Define custom root AFTER serve_tty
        create_custom_root_endpoint(app)
        
    elif mode == "user_root_before":
        # 7. Custom User Root Before Terminaide
        description = MODE_DESCRIPTIONS[mode]
        # Define custom root BEFORE serve_tty
        create_custom_root_endpoint(app)
        serve_tty(
            app,
            script_routes={
                "/terminal1": CLIENT_SCRIPT,  # Normal mode
                "/terminal2": [CLIENT_SCRIPT, "--alternate"]  # With --alternate flag
            },
            title="User Root Before",
            debug=True
        )
        
    else:
        raise ValueError(f"Unknown mode: {mode}")
    
    # Add info endpoint
    create_info_endpoint(app, mode, description)
    
    return app

def get_application():
    """Factory function for creating the FastAPI application.
    This enables Uvicorn's reload feature to work properly."""
    return create_app(CURRENT_MODE)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Terminaide test server with multiple configuration modes."
    )
    parser.add_argument(
        "--mode",
        choices=list(MODE_DESCRIPTIONS.keys()),
        default="demo",
        help="Configuration mode to test (default: demo)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000)"
    )
    return parser.parse_args()

def log_server_info(mode, port):
    """Log information about the server configuration."""
    logger.info(f"Starting server in {mode.upper()} mode on port {port}")
    logger.info(f"Visit http://localhost:{port} to see the main interface")
    logger.info(f"Visit http://localhost:{port}/info for configuration details")
    
    # For modes with terminals at other paths, display the URLs
    if mode not in ["single", "demo"]:
        logger.info("Available terminal routes:")
        
        # Show root terminal info
        if mode not in ["user_root_after", "user_root_before"]:
            if mode in ["multi_with_root", "combined", "single"]:
                logger.info(f"  / - Terminal running client.py")
            else:
                logger.info(f"  / - Demo terminal")
        
        # For multi-script modes
        if mode in ["multi_no_root", "multi_with_root", "combined", "user_root_after", "user_root_before"]:
            logger.info(f"  /terminal1 - Terminal running client.py (standard mode)")
            logger.info(f"  /terminal2 - Terminal running client.py --alternate")

def main():
    """Main function to run the server."""
    args = parse_args()
    
    # Store current configuration in global variables for factory function
    global CURRENT_MODE, CURRENT_PORT
    CURRENT_MODE = args.mode
    CURRENT_PORT = args.port
    
    # Log server information
    log_server_info(args.mode, args.port)
    
    # Start the server with uvicorn - using a factory approach for reload compatibility
    import uvicorn
    
    # Use the 'app' factory function with reload instead of a direct app instance
    uvicorn.run(
        "server:get_application",  # Use factory function path
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        reload=True,
        reload_dirs=[str(CURRENT_DIR.parent)],
        factory=True  # Tell Uvicorn this is a factory function
    )

if __name__ == '__main__':
    main()