#!/usr/bin/env python3
# tests/server.py

"""
Test server for terminaide that supports multiple configuration patterns.

This script demonstrates key ways of configuring and running terminaide:

Usage:
    python server.py                        # Default mode - shows instructions demo
    python server.py --mode single          # Single application with Termin-Arcade menu
    python server.py --mode multi           # HTML page at root, terminal games at routes
    python server.py --mode container       # Run the server in a Docker container
"""

import argparse
import logging
import os
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Optional, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from terminaide import serve_tty

import uvicorn

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
    """Add a custom root endpoint to the app that returns HTML."""
    @app.get("/", response_class=HTMLResponse)
    async def custom_root(request: Request):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Termin-Arcade</title>
            <link rel="icon" type="image/x-icon" href="{request.url_for('static', path='favicon.ico')}">
            <style>
                body {{
                    font-family: 'Courier New', monospace;
                    line-height: 1.5;
                    color: #f0f0f0;
                    background-color: black;
                    text-align: center;
                    padding: 40px 20px;
                    margin: 0;
                }}
                h1 {{
                    color: #3498db;
                    border-bottom: 1px solid #3498db;
                    padding-bottom: 15px;
                    margin: 0 auto 30px;
                    max-width: 600px;
                }}
                .card {{
                    background-color: #2d2d2d;
                    max-width: 600px;
                    margin: 0 auto 30px;
                    padding: 20px;
                }}
                .terminal-box {{
                    border: 1px solid #3498db;
                    max-width: 400px;
                    margin: 30px auto;
                    padding: 10px;
                }}
                .links {{
                    display: flex;
                    justify-content: center;
                    gap: 20px;
                    margin: 30px auto;
                }}
                .terminal-link {{
                    display: inline-block;
                    background-color: #3498db;
                    color: #000;
                    padding: 8px 20px;
                    text-decoration: none;
                    font-weight: bold;
                }}
                .info-link {{
                    color: #3498db;
                    text-decoration: none;
                    margin-top: 40px;
                    display: inline-block;
                }}
            </style>
        </head>
        <body>
            <h1>Termin-Arcade</h1>
            
            <div class="card">
                This demo shows how HTML pages and terminal applications can be combined in one server.
                Each game runs in its own terminal instance.
            </div>
            
            <div class="terminal-box">
                Available Terminal Games
            </div>
            
            <div class="links">
                <a href="/snake" class="terminal-link">Snake</a>
                <a href="/tetris" class="terminal-link">Tetris</a>
                <a href="/pong" class="terminal-link">Pong</a>
            </div>
            
            <a href="/info" class="info-link">Server Configuration Info</a>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)


def create_info_endpoint(app: FastAPI, mode: str, description: str):
    """Add an info endpoint that explains the current configuration."""
    @app.get("/info", response_class=HTMLResponse)
    async def info(request: Request):
        info_dict = {
            "mode": mode,
            "description": description,
            "client_script": str(CLIENT_SCRIPT),
            "modes": {
                "default": "Default configuration - shows instructions demo",
                "single": "Single application with Termin-Arcade menu",
                "multi": "HTML page at root, terminal games at separate routes",
                "container": "Run server in a Docker container"
            },
            "usage": "Change mode by running with --mode [mode_name]",
            "notes": [
                "Route priority: User-defined routes take precedence over terminaide routes",
                "Order of route definition matters",
                "Custom routes can be defined before or after serve_tty() with different results"
            ]
        }
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Terminaide Info</title>
    <link rel="icon" type="image/x-icon" href="{request.url_for('static', path='favicon.ico')}">
</head>
<body>
    <pre>{json.dumps(info_dict, indent=2)}</pre>
</body>
</html>"""


def create_app() -> FastAPI:
    """
    Factory function that Uvicorn will import and call on each reload.

    Reads the mode from the environment instead of a global variable so that
    watchfiles reload can re-import this factory.
    
    Important notes about terminaide configuration:
    
    1. Route Priority: When both a custom route and a terminaide route target 
       the same path, the one defined FIRST in the code takes precedence.
    
    2. Root Path Handling: If you want your own content at the root path (/),
       either define your route BEFORE calling serve_tty() or don't specify
       a client_script or root path in script_routes when calling serve_tty().
    
    3. Configuration Interactions: 
       - If client_script is provided, it runs at the root path (/)
       - If script_routes includes "/", it overrides the default behavior
       - If neither is specified, terminaide shows its instructions demo
    
    4. FastAPI Integration: Terminaide works seamlessly with existing FastAPI
       applications, but be mindful of route conflicts and priorities.
    """
    # Get mode from environment or use default
    mode = os.environ.get("TERMINAIDE_MODE", "default")
    app = FastAPI(title=f"Terminaide Test - {mode.upper()} Mode")

    # We declare a local variable to describe the current configuration
    description = ""

    # Mode-specific configuration
    if mode == "default":
        # Default mode: no client script, no script routes
        # Important: In this configuration, terminaide will show its built-in instructions demo
        description = "Default configuration - shows instructions demo"
        serve_tty(
            app,
            title="Default Mode",
            debug=True
        )
        
    elif mode == "single":
        # Single mode: One cohesive application with internal navigation
        # The index.py script serves as a menu that can launch different games
        description = "Single application with Termin-Arcade menu"
        serve_tty(
            app,
            client_script=[CLIENT_SCRIPT, "--index"],
            title="Termin-Arcade",
            debug=True
        )
        
    elif mode == "multi":
        # Multi mode: HTML page at root + separate terminal routes for games
        # This demonstrates how terminaide can be integrated with regular web pages
        description = "HTML page at root, terminal games at separate routes"
        
        # Define custom HTML root BEFORE serve_tty
        # Note: Order matters! The first route defined for a path takes precedence.
        create_custom_root_endpoint(app)
        
        # Configure separate routes for each game
        serve_tty(
            app,
            script_routes={
                "/snake": [CLIENT_SCRIPT, "--snake"],
                "/tetris": [CLIENT_SCRIPT, "--tetris"],
                "/pong": [CLIENT_SCRIPT, "--pong"]
            },
            title="Termin-Arcade Games",
            debug=True
        )
        
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Add info endpoint
    create_info_endpoint(app, mode, description)

    return app


def generate_requirements_txt(pyproject_path, temp_dir):
    """
    Generate requirements.txt from pyproject.toml including all dependencies except those in the dev group.
    
    Args:
        pyproject_path: Path to pyproject.toml file
        temp_dir: Directory to save requirements.txt
    
    Returns:
        Path: Path to generated requirements.txt
    """
    try:
        logger.info("Generating requirements.txt from pyproject.toml (including all except dev dependencies)")
        req_path = Path(temp_dir) / "requirements.txt"
        
        # Use poetry to export dependencies, excluding dev dependencies
        result = subprocess.run(
            ["poetry", "export", "--without", "dev", "--format", "requirements.txt"],
            cwd=pyproject_path.parent,
            capture_output=True,
            text=True,
            check=True
        )
        with open(req_path, "w") as f:
            f.write(result.stdout)
            
        logger.info(f"Requirements file generated at {req_path}")
        return req_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to generate requirements: {e}")
        logger.error(f"Poetry output: {e.stderr}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to generate requirements: {e}")
        sys.exit(1)


def build_and_run_container(port=8000):
    """
    Build Docker image and run container using Docker SDK.
    
    Args:
        port: Port to expose from the container
    """
    try:
        # Import docker here to avoid dependency issues if not installed
        try:
            import docker
        except ImportError:
            logger.error("Docker SDK not installed. Please install it with: poetry add docker --group dev")
            logger.error("Or run: pip install docker")
            sys.exit(1)
            
        # Connect to Docker daemon
        client = docker.from_env()
        client.ping()
        logger.info("Successfully connected to Docker daemon")
        
        # Get project directory
        project_root = Path(__file__).parent.parent.absolute()
        logger.info(f"Project root: {project_root}")
        
        # Image name based on directory name
        image_name = project_root.name.lower()
        
        # Create a temporary directory for the build context
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Copy required directories to the temporary directory
            logger.info("Preparing build context...")
            for directory in ["terminaide", "tests"]:
                src_dir = project_root / directory
                dst_dir = temp_path / directory
                if src_dir.exists():
                    shutil.copytree(src_dir, dst_dir)
            
            # Generate requirements.txt from pyproject.toml
            generate_requirements_txt(project_root / "pyproject.toml", temp_path)
            
            # Create Dockerfile in the temporary directory
            dockerfile_content = """
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Copy only what's needed
COPY terminaide/ ./terminaide/
COPY tests/ ./tests/
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["python", "tests/server.py", "--mode", "multi"]
"""
            dockerfile_path = temp_path / "Dockerfile"
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
            
            # Build Docker image
            logger.info(f"Building Docker image: {image_name}")
            image, build_logs = client.images.build(
                path=str(temp_path),
                tag=image_name,
                rm=True
            )
            
            # Print build logs
            for log in build_logs:
                if 'stream' in log:
                    log_line = log['stream'].strip()
                    if log_line:
                        logger.info(f"Build: {log_line}")
            
            logger.info(f"Successfully built image: {image.tags}")
        
        # Check for existing container with the same name and remove it
        container_name = f"{image_name}-container"
        try:
            old_container = client.containers.get(container_name)
            logger.info(f"Found existing container {container_name}, removing...")
            old_container.stop()
            old_container.remove()
            logger.info(f"Removed container {container_name}")
        except docker.errors.NotFound:
            pass
        
        # Run the container
        logger.info(f"Starting container {container_name} on port {port}")
        container = client.containers.run(
            image.id,
            name=container_name,
            ports={f"8000/tcp": port},
            detach=True
        )
        
        logger.info(f"Container started with ID: {container.id[:12]}")
        logger.info(f"Access the terminal at: http://localhost:{port}")
        
        # Stream container logs with graceful exit handling
        logger.info("Container logs:")
        logger.info("Press Ctrl+C to stop the container and exit")
        try:
            for log in container.logs(stream=True):
                print(log.decode().strip())
        except KeyboardInterrupt:
            logger.info("\nReceived interrupt signal, stopping container...")
            container.stop()
            logger.info(f"Container {container_name} stopped successfully")
            return
            
    except Exception as e:
        if "docker" in str(e.__class__):
            logger.error(f"Docker error: {e}")
            logger.error("Make sure Docker is installed and running")
        else:
            logger.error(f"Error: {e}")
        sys.exit(1)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Test server for terminaide with different configuration patterns."
    )
    parser.add_argument(
        "--mode",
        choices=["default", "single", "multi", "container"],
        default="default",
        help="Which configuration pattern to test (default: default)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000)"
    )
    return parser.parse_args()


def main():
    """
    Main function that handles all modes including container mode.
    We store --mode in an environment variable for create_app() to use
    when running in non-container modes.
    """
    args = parse_args()

    # Set mode in an env variable so create_app() sees it on reload
    os.environ["TERMINAIDE_MODE"] = args.mode

    # Common log message about port for all modes
    logger.info(f"Using port {args.port} for all operations")

    # Handle special container mode
    if args.mode == "container":
        logger.info(f"Starting container mode")
        build_and_run_container(port=args.port)
        return

    # Normal server modes
    logger.info(f"Starting server in {args.mode.upper()} mode")
    logger.info(f"Visit http://localhost:{args.port} to see the main interface")
    logger.info(f"Visit http://localhost:{args.port}/info for configuration details")

    # Mode-specific information
    if args.mode == "default":
        logger.info("Default mode - showing built-in instructions demo")
    elif args.mode == "single":
        logger.info("Single mode - Termin-Arcade menu at root path (/)")
        logger.info("Menu provides access to Snake, Tetris, and Pong games")
    elif args.mode == "multi":
        logger.info("Multi mode - HTML page at root with links to:")
        logger.info("  /snake - Snake Game")
        logger.info("  /tetris - Tetris Game")
        logger.info("  /pong - Pong Game")

    uvicorn.run(
        "tests.server:create_app",
        factory=True,
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        reload=True,
        reload_dirs=[str(CURRENT_DIR.parent)]
    )


if __name__ == '__main__':
    main()