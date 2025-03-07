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
from pathlib import Path
from typing import Dict, Optional, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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

def create_custom_root_endpoint(app: FastAPI):
    """Add a custom root endpoint to the app."""
    @app.get("/")
    async def custom_root():
        return {
            "message": "This is a custom root endpoint",
            "info": "This route is defined by the user, not by terminaide",
            "note": "This demonstrates that user-defined routes take precedence"
        }

def create_info_endpoint(app: FastAPI, mode: str, description: str):
    """Add an info endpoint that explains the current configuration."""
    @app.get("/info")
    async def info():
        return {
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
        
def create_app(mode: str) -> FastAPI:
    """Create and configure a FastAPI app based on the specified mode."""
    
    app = FastAPI(title=f"Terminaide Test - {mode.upper()} Mode")
    
    # Mode-specific configuration
    if mode == "single":
        # 1. Single Script (Basic Usage)
        description = "Single script at root path - client.py runs at /"
        serve_tty(
            app,
            client_script=CLIENT_SCRIPT,
            title="Single Script Mode",
            debug=True
        )
        
    elif mode == "demo":
        # 2. No Script Specified (Demo Mode)
        description = "No script specified - demo runs at root path"
        serve_tty(
            app,
            title="Demo Mode",
            debug=True
        )
        
    elif mode == "multi_no_root":
        # 3. Multiple Scripts Without Root
        description = "Multiple scripts without root - demo at /, other scripts at paths"
        serve_tty(
            app,
            script_routes={
                "/terminal1": CLIENT_SCRIPT,
                "/terminal2": CLIENT_SCRIPT
            },
            title="Multi-Script No Root",
            debug=True
        )
        
    elif mode == "multi_with_root":
        # 4. Multiple Scripts With Root
        description = "Multiple scripts with root - client.py at /, others at paths"
        serve_tty(
            app,
            script_routes={
                "/": CLIENT_SCRIPT,
                "/terminal1": CLIENT_SCRIPT,
                "/terminal2": CLIENT_SCRIPT
            },
            title="Multi-Script With Root",
            debug=True
        )
        
    elif mode == "combined":
        # 5. Combined Approaches
        description = "Combined approaches - client_script and script_routes"
        serve_tty(
            app,
            client_script=CLIENT_SCRIPT,
            script_routes={
                "/terminal1": CLIENT_SCRIPT,
                "/terminal2": CLIENT_SCRIPT
            },
            title="Combined Approach",
            debug=True
        )
        
    elif mode == "user_root_after":
        # 6. Custom User Root After Terminaide
        description = "User defines root AFTER terminaide - user route wins"
        serve_tty(
            app,
            script_routes={
                "/terminal1": CLIENT_SCRIPT,
                "/terminal2": CLIENT_SCRIPT
            },
            title="User Root After",
            debug=True
        )
        # Define custom root AFTER serve_tty
        create_custom_root_endpoint(app)
        
    elif mode == "user_root_before":
        # 7. Custom User Root Before Terminaide
        description = "User defines root BEFORE terminaide - user route wins"
        # Define custom root BEFORE serve_tty
        create_custom_root_endpoint(app)
        serve_tty(
            app,
            script_routes={
                "/terminal1": CLIENT_SCRIPT,
                "/terminal2": CLIENT_SCRIPT
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
        choices=["single", "demo", "multi_no_root", "multi_with_root", "combined", 
                 "user_root_after", "user_root_before"],
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
    """Main function to run the server."""
    args = parse_args()
    
    # Create app with the specified mode
    app = create_app(args.mode)
    
    # Log server information
    logger.info(f"Starting server in {args.mode.upper()} mode on port {args.port}")
    logger.info(f"Visit http://localhost:{args.port} to see the main interface")
    logger.info(f"Visit http://localhost:{args.port}/info for configuration details")
    
    # For modes with terminals at other paths, display the URLs
    if args.mode not in ["single", "demo"]:
        logger.info("Available terminal routes:")
        if args.mode not in ["user_root_after", "user_root_before"]:
            # Root is a terminal in these modes
            if args.mode in ["multi_with_root", "combined", "single"]:
                logger.info(f"  / - Terminal running client.py")
            else:
                logger.info(f"  / - Demo terminal")
        
        # For multi-script modes
        if args.mode in ["multi_no_root", "multi_with_root", "combined", "user_root_after", "user_root_before"]:
            logger.info(f"  /terminal1 - Terminal running client.py")
            logger.info(f"  /terminal2 - Terminal running client.py")
    
    # Directly use uvicorn.run with the created app instance
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_level="info"
    )

if __name__ == '__main__':
    main()