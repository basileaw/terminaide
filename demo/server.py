#!/usr/bin/env python3
# demo/server.py

"""
Test server for terminaide that supports multiple configuration patterns.

Usage:
    python server.py                     # Default mode - shows getting started interface
    python server.py single              # Single application with Termin-Arcade menu
    python server.py multi               # HTML page at root, terminal games at routes
    python server.py container           # Run the server in a Docker container
"""

import os
import sys
import json
import shutil
import logging
import argparse
import tempfile
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from terminaide import serve_terminal

import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:     %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent
CLIENT_SCRIPT = CURRENT_DIR / "client.py"


def create_custom_root_endpoint(app: FastAPI):
    """Add an HTML root with rainbow ASCII banner and white for borders/buttons."""
    @app.get("/", response_class=HTMLResponse)
    async def custom_root(request: Request):
        # If CONTAINER_MODE is set, we show "Container" instead of "Multi"
        title_mode = "Container" if os.environ.get("CONTAINER_MODE") == "true" else "Multi"

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Termin-Arcade ({title_mode})</title>
    <link rel="icon" type="image/x-icon" href="{request.url_for('static', path='favicon.ico')}">
    <style>
        body {{
            font-family: 'Courier New', monospace;
            line-height: 1.5;
            background-color: black;
            color: #f0f0f0;
            text-align: center;
            padding: 40px 20px;
            margin: 0;
        }}
        .ascii-banner pre {{
            margin: 0 auto 40px;
            white-space: pre;
            line-height: 1;
            display: inline-block;
            text-align: left;
            /* Rainbow gradient for the ASCII text */
            background: linear-gradient(
                to right,
                red,
                orange,
                yellow,
                green,
                blue,
                indigo,
                violet
            );
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            color: transparent; /* fallback for older browsers */
        }}
        .card {{
            background-color: #2d2d2d;
            max-width: 600px;
            margin: 0 auto 30px;
            padding: 20px;
        }}
        .terminal-box {{
            border: 1px solid #fff;  /* White border */
            max-width: 400px;
            margin: 30px auto;
            padding: 10px;
            color: #fff;             /* White text */
        }}
        .links {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin: 30px auto;
        }}
        .terminal-link {{
            display: inline-block;
            background-color: #fff;  /* White background */
            color: #000;             /* Black text */
            padding: 8px 20px;
            text-decoration: none;
            font-weight: bold;
        }}
        .info-link {{
            color: #fff;            /* White text */
            text-decoration: none;
            display: inline-block;
        }}
    </style>
</head>
<body>
    <div class="ascii-banner">
<pre>████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗      █████╗ ██████╗  ██████╗ █████╗ ██████╗ ███████╗
╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝
   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║     ███████║██████╔╝██║     ███████║██║  ██║█████╗  
   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║     ██╔══██║██╔══██╗██║     ██╔══██║██║  ██║██╔══╝  
   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║     ██║  ██║██║  ██║╚██████╗██║  ██║██████╔╝███████╗
   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═════╝ ╚══════╝</pre>
    </div>

    <div class="card">
        This demo shows how HTML pages and terminal applications can be combined in one server.
        Each game runs in its own terminal instance.
    </div>

    <div class="terminal-box">
        Available Games
    </div>

    <div class="links">
        <a href="/snake" class="terminal-link">Snake</a>
        <a href="/tetris" class="terminal-link">Tetris</a>
        <a href="/pong" class="terminal-link">Pong</a>
    </div>

    <a href="/info" class="info-link">Server Configuration Info</a>
</body>
</html>"""
        return HTMLResponse(html_content)


def create_info_endpoint(app: FastAPI, mode: str, description: str):
    """Add an info endpoint that explains the current configuration."""
    @app.get("/info", response_class=HTMLResponse)
    async def info(request: Request):
        info_dict = {
            "mode": mode,
            "description": description,
            "client_script": str(CLIENT_SCRIPT),
            "modes": {
                "default": "Default config - built-in interface",
                "single": "Single app with Termin-Arcade menu",
                "multi": "HTML page at root + terminal games",
                "container": "Run inside Docker container"
            },
            "usage": "python server.py [mode] or python server.py --mode [mode]",
            "notes": [
                "Route priority: custom routes > terminaide routes",
                "Order of route definition matters",
                "Custom routes can be defined before or after serve_terminal()"
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
    Factory function for Uvicorn (with reload).
    """
    mode = os.environ.get("TERMINAIDE_MODE", "default")
    app = FastAPI(title=f"Terminaide Test - {mode.upper()} Mode")

    description = ""

    if mode == "default":
        description = "Default configuration - shows built-in interface"
        serve_terminal(app, title="Default Mode", debug=True)
    elif mode == "single":
        description = "Single application with Termin-Arcade menu"
        serve_terminal(
            app,
            client_script=[CLIENT_SCRIPT, "--index"],
            title="Termin-Arcade (Single)",
            debug=True
        )
    elif mode == "multi":
        description = "HTML root page + separate terminal routes"
        create_custom_root_endpoint(app)
        serve_terminal(
            app,
            terminal_routes={
                "/snake": {
                    "client_script": [CLIENT_SCRIPT, "--snake"],
                    "title": "Termin-Arcade (Snake)"
                },
                "/tetris": {
                    "client_script": [CLIENT_SCRIPT, "--tetris"],
                    "title": "Termin-Arcade (Tetris)"
                },
                "/pong": {
                    "client_script": [CLIENT_SCRIPT, "--pong"],
                    "title": "Termin-Arcade (Pong)"
                }
            },
            debug=True
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")

    create_info_endpoint(app, mode, description)
    return app


def generate_requirements_txt(pyproject_path, temp_dir):
    """
    Generate requirements.txt from pyproject.toml, excluding dev dependencies.
    """
    try:
        logger.info("Generating requirements.txt (excluding dev)")
        req_path = Path(temp_dir) / "requirements.txt"
        
        result = subprocess.run(
            [
                "poetry",
                "export",
                "--with", "demo",
                "--without", "dev",
                "--format", "requirements.txt"
            ],
            cwd=pyproject_path.parent,
            capture_output=True,
            text=True,
            check=True
        )

        with open(req_path, "w") as f:
            f.write(result.stdout)

        logger.info(f"Requirements file at {req_path}")
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
    Build a Docker image and run it using the Docker SDK.
    """
    try:
        try:
            import docker
        except ImportError:
            logger.error("Install docker SDK: 'poetry add docker --group dev' or 'pip install docker'")
            sys.exit(1)
            
        client = docker.from_env()
        client.ping()
        logger.info("Connected to Docker daemon")
        
        project_root = Path(__file__).parent.parent.absolute()
        image_name = project_root.name.lower()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Copy source to build context
            for directory in ["terminaide", "demo"]:
                src_dir = project_root / directory
                dst_dir = temp_path / directory
                if src_dir.exists():
                    shutil.copytree(src_dir, dst_dir)
            
            # Generate requirements
            generate_requirements_txt(project_root / "pyproject.toml", temp_path)
            
            dockerfile_content = """
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
WORKDIR /app

COPY terminaide/ ./terminaide/
COPY demo/ ./demo/
COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000

CMD ["python", "demo/server.py", "--mode", "multi"]
"""
            dockerfile_path = temp_path / "Dockerfile"
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
            
            logger.info(f"Building Docker image: {image_name}")
            image, build_logs = client.images.build(
                path=str(temp_path),
                tag=image_name,
                rm=True
            )
            for log in build_logs:
                if 'stream' in log:
                    log_line = log['stream'].strip()
                    if log_line:
                        logger.info(f"Build: {log_line}")
            
            logger.info(f"Image built: {image.tags}")
        
        container_name = f"{image_name}-container"
        # Remove old container if exists
        try:
            old_container = client.containers.get(container_name)
            old_container.stop()
            old_container.remove()
        except docker.errors.NotFound:
            pass
        
        logger.info(f"Starting container {container_name} on port {port}")
        container = client.containers.run(
            image.id,
            name=container_name,
            ports={f"8000/tcp": port},
            detach=True,
            environment={"CONTAINER_MODE": "true"}
        )
        
        logger.info(f"Container {container_name} started, ID: {container.id[:12]}")
        logger.info(f"Access at: http://localhost:{port}")
        logger.info("Streaming container logs (Ctrl+C to stop)")

        try:
            for log_line in container.logs(stream=True):
                print(log_line.decode().strip())
        except KeyboardInterrupt:
            logger.info("Stopping container...")
            container.stop()
            logger.info("Container stopped")
            
    except Exception as e:
        if "docker" in str(e.__class__):
            logger.error(f"Docker error: {e}")
            logger.error("Ensure Docker is installed and running")
        else:
            logger.error(f"Error: {e}")
        sys.exit(1)


def parse_args():
    """Parse command line arguments with positional or --mode flag."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode_pos",
        nargs="?",
        choices=["default", "single", "multi", "container"],
        default="default",
        help="Server mode (positional arg)"
    )
    parser.add_argument(
        "--mode",
        choices=["default", "single", "multi", "container"],
        help="Server mode (overrides positional arg)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the server"
    )
    args = parser.parse_args()

    if args.mode is not None:
        args.actual_mode = args.mode
    else:
        args.actual_mode = args.mode_pos
    return args


def main():
    """
    Main entrypoint for running in different modes.
    """
    args = parse_args()
    mode = args.actual_mode
    
    os.environ["TERMINAIDE_MODE"] = mode
    logger.info(f"Starting server in {mode.upper()} mode on port {args.port}")

    if mode == "container":
        build_and_run_container(port=args.port)
        return

    logger.info(f"Visit http://localhost:{args.port} for the main interface")
    logger.info(f"Visit http://localhost:{args.port}/info for details")

    uvicorn.run(
        "demo.server:create_app",
        factory=True,
        host="0.0.0.0",
        port=args.port,
        reload=True,
        reload_dirs=[str(CURRENT_DIR.parent)]
    )


if __name__ == '__main__':
    main()
