# server.py

"""
Test server for terminaide that demonstrates all three API tiers.
Usage:
python demo/server.py                     # Default mode - shows getting started interface
python demo/server.py --function          # Function mode - demo of serve_function() with Asteroids
python demo/server.py --script            # Script mode - demo of serve_script()
python demo/server.py --apps              # Apps mode - HTML page at root, terminal games at routes
python demo/server.py --container         # Run the apps mode in a Docker container
"""

import os
import sys
import json
import shutil
import uvicorn
import argparse
import tempfile
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast, TypeVar, Type, Mapping, Tuple
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# Add project root to path to ensure imports work correctly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from terminaide import logger
from terminaide import serve_function, serve_script, serve_apps

CURRENT_DIR = Path(__file__).parent
CLIENT_SCRIPT = CURRENT_DIR / "client.py"
# Convert project_root to a Path object for path operations
project_root_path = Path(project_root)
INSTRUCTIONS_PATH = project_root_path / "terminarcade" / "instructions.py"

MODE_HELP = {
    "default": "Default (getting started interface)",
    "function": "Serve function mode (Asteroids)",
    "script": "Serve script mode",
    "apps": "Apps mode (HTML + routes)",
    "container": "Docker container mode (same as apps)",
}

# Type alias for dynamic Docker client handling
T = TypeVar("T")


def create_custom_root_endpoint(app: FastAPI) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def custom_root(request: Request) -> HTMLResponse:
        title_mode = (
            "Container" if os.environ.get("CONTAINER_MODE") == "true" else "Apps"
        )
        html_content = f"""<!DOCTYPE html>
        <html>
        <head>
            <title>{title_mode} Mode</title>
            <link rel="icon" type="image/x-icon" href="/terminaide-static/favicon.ico">
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
                    color: transparent;
                }}
                .card {{
                    background-color: #2d2d2d;
                    max-width: 600px;
                    margin: 0 auto 30px;
                    padding: 20px;
                }}
                .terminal-box {{
                    border: 1px solid #fff;
                    max-width: 400px;
                    margin: 30px auto;
                    padding: 10px;
                    color: #fff;
                }}
                .links {{
                    display: flex;
                    justify-content: center;
                    gap: 20px;
                    margin: 30px auto;
                }}
                .terminal-link {{
                    display: inline-block;
                    background-color: #fff;
                    color: #000;
                    padding: 8px 20px;
                    text-decoration: none;
                    font-weight: bold;
                }}
                .info-link {{
                    color: #fff;
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
        return HTMLResponse(content=html_content)


def create_info_endpoint(app: FastAPI, mode: str, description: str) -> None:
    @app.get("/info", response_class=HTMLResponse)
    async def info(request: Request) -> HTMLResponse:
        info_dict = {
            "mode": mode,
            "description": description,
            "client_script": str(CLIENT_SCRIPT),
            "modes": MODE_HELP,
            "usage": "python demo/server.py [--default|--function|--script|--apps|--container]",
            "notes": [
                "serve_function: Simplest - just pass a function",
                "serve_script: Simple - pass a script file",
                "serve_apps: Advanced - integrate with FastAPI",
            ],
        }
        html_content = f"""<!DOCTYPE html>
        <html>
        <head>
            <title>Terminaide Info</title>
            <link rel="icon" type="image/x-icon" href="/terminaide-static/favicon.ico">
        </head>
        <body><pre>{json.dumps(info_dict, indent=2)}</pre></body>
        </html>"""
        return HTMLResponse(content=html_content)


def play_asteroids_function() -> None:
    from terminarcade import play_asteroids

    play_asteroids()


def create_app() -> FastAPI:
    """
    Factory function: read mode from environment, build and return FastAPI app.
    Used by Uvicorn with 'factory=True' so it can reload properly.
    """
    mode = os.environ.get("TERMINAIDE_MODE", "default")
    app = FastAPI(title=f"Terminaide - {mode.upper()} Mode")
    description = ""

    # Don't try to use any Docker stuff here - just handle the apps mode
    if mode == "apps":
        description = "Apps mode - HTML root + separate terminal routes"
        create_custom_root_endpoint(app)
        serve_apps(
            app,
            terminal_routes={
                "/snake": {
                    "client_script": [CLIENT_SCRIPT, "--snake"],
                    "title": "Termin-Arcade (Snake)",
                },
                "/tetris": {
                    "client_script": [CLIENT_SCRIPT, "--tetris"],
                    "title": "Termin-Arcade (Tetris)",
                },
                "/pong": {
                    "client_script": [CLIENT_SCRIPT, "--pong"],
                    "title": "Termin-Arcade (Pong)",
                },
            },
            debug=True,
        )
        create_info_endpoint(app, mode, description)

    return app


def generate_requirements_txt(pyproject_path: Path, temp_dir: Union[str, Path]) -> Path:
    try:
        import re

        logger.info("Generating requirements.txt (excluding demo)")
        req_path = Path(temp_dir) / "requirements.txt"

        # Read pyproject.toml
        with open(pyproject_path, "r") as f:
            content = f.read()

        # Find the main dependencies section
        deps_section = re.search(
            r"\[tool\.poetry\.dependencies\](.*?)(?=\[tool\.poetry|$)",
            content,
            re.DOTALL,
        )

        if not deps_section:
            raise ValueError("No dependencies section found in pyproject.toml")

        deps = []
        # Extract package names using regex, one per line
        for line in deps_section.group(1).strip().split("\n"):
            # Skip empty lines and the python requirement
            if not line.strip() or line.strip().startswith("python"):
                continue

            # Extract package name (part before =, ^ or spaces)
            match = re.match(r"([a-zA-Z0-9_-]+)\s*=", line.strip())
            if match:
                package = match.group(1).strip()
                deps.append(package)

        if not deps:
            raise ValueError("No dependencies found in pyproject.toml")

        # Write to requirements.txt
        with open(req_path, "w") as f:
            for dep in deps:
                f.write(f"{dep}\n")

        logger.info(f"Requirements file at {req_path}")
        return req_path
    except Exception as e:
        logger.error(f"Failed to generate requirements: {e}")
        sys.exit(1)


def get_exception_class(module: Any, name: str) -> Type[Exception]:
    """Safe helper to get exception classes from modules"""
    try:
        if hasattr(module, "errors") and hasattr(module.errors, name):
            return getattr(module.errors, name)
        return Exception  # Fallback to base Exception
    except (AttributeError, ImportError):
        return Exception


def build_and_run_container_subprocess(port: int = 8000) -> None:
    """Alternative implementation using subprocess instead of docker package"""
    # Check if docker is installed
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("Docker is not installed or not in PATH")
        sys.exit(1)

    # Implementation using subprocess commands instead of docker package
    # (Simplified version of the same functionality)
    project_root = Path(__file__).parent.parent.absolute()
    image_name = project_root.name.lower()

    # Create temp directory and generate files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        # Copy directories
        for directory in ["terminaide", "terminarcade", "demo"]:
            src_dir = project_root / directory
            dst_dir = temp_path / directory
            if src_dir.exists():
                shutil.copytree(
                    src_dir,
                    dst_dir,
                    ignore=lambda src, names: (
                        ["ttyd"] if os.path.basename(src) == "bin" else []
                    ),
                )
                if directory == "terminaide":
                    (dst_dir / "core" / "bin").mkdir(exist_ok=True)

        # Generate requirements
        generate_requirements_txt(project_root / "pyproject.toml", temp_path)

        # Create Dockerfile
        dockerfile_content = """
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
WORKDIR /app
COPY terminaide/ ./terminaide/
COPY terminarcade/ ./terminarcade/
COPY demo/ ./demo/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
CMD ["python", "demo/server.py", "apps"]
"""
        dockerfile_path = temp_path / "Dockerfile"
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)

        # Build image using subprocess
        logger.info(f"Building Docker image: {image_name}")
        build_cmd = ["docker", "build", "-t", image_name, str(temp_path)]
        result = subprocess.run(build_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Docker build failed: {result.stderr}")
            sys.exit(1)

        # Check for existing container
        container_name = f"{image_name}-container"
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={container_name}",
                "--format",
                "{{.ID}}",
            ],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            logger.info(f"Stopping existing container: {container_name}")
            subprocess.run(["docker", "stop", container_name], capture_output=True)
            subprocess.run(["docker", "rm", container_name], capture_output=True)

        # Run container
        logger.info(f"Starting container {container_name} on port {port}")
        run_cmd = [
            "docker",
            "run",
            "--name",
            container_name,
            "-p",
            f"{port}:8000",
            "-e",
            "CONTAINER_MODE=true",
            "-d",
            image_name,
        ]
        result = subprocess.run(run_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Docker run failed: {result.stderr}")
            sys.exit(1)

        container_id = result.stdout.strip()
        logger.info(f"Container {container_name} started (ID: {container_id[:12]})")
        logger.info(f"Access at: http://localhost:{port}")
        logger.info("Streaming container logs (Ctrl+C to stop)")

        try:
            # Stream logs
            log_cmd = ["docker", "logs", "-f", container_id]
            subprocess.run(log_cmd)
        except KeyboardInterrupt:
            logger.info("Stopping container...")
            subprocess.run(["docker", "stop", container_id], capture_output=True)
            logger.info("Container stopped")


def build_and_run_container(port: int = 8000) -> None:
    try:
        # First check if docker package is available
        docker_available = False
        docker_module = None
        try:
            import docker

            docker_available = True
            docker_module = docker
        except ImportError:
            logger.info(
                "Docker Python package not available, falling back to subprocess implementation"
            )
            return build_and_run_container_subprocess(port)

        if not docker_available or docker_module is None:
            return build_and_run_container_subprocess(port)

        # Initialize client variable to avoid "possibly unbound" errors
        client = None

        # Continue with docker package implementation if available
        # Get the correct Docker socket location from the context
        context_result = subprocess.run(
            ["docker", "context", "inspect"], capture_output=True, text=True
        )
        if context_result.returncode == 0:
            context_data = json.loads(context_result.stdout)
            if context_data and "Endpoints" in context_data[0]:
                docker_host = context_data[0]["Endpoints"]["docker"]["Host"]
                client = docker_module.DockerClient(base_url=docker_host)
        else:
            client = docker_module.from_env()

        if client is None:
            logger.error("Failed to initialize Docker client")
            return build_and_run_container_subprocess(port)

        client.ping()

        logger.info("Connected to Docker daemon")
        project_root = Path(__file__).parent.parent.absolute()
        image_name = project_root.name.lower()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Update directory list - now includes demo directory
            for directory in ["terminaide", "terminarcade", "demo"]:
                src_dir = project_root / directory
                dst_dir = temp_path / directory
                if src_dir.exists():
                    # Basic solution - ensure bin directory exists but is empty
                    shutil.copytree(
                        src_dir,
                        dst_dir,
                        ignore=lambda src, names: (
                            ["ttyd"] if os.path.basename(src) == "bin" else []
                        ),
                    )
                    # Alternatively, create an empty bin directory if it was excluded
                    if directory == "terminaide":
                        (dst_dir / "core" / "bin").mkdir(exist_ok=True)

            generate_requirements_txt(project_root / "pyproject.toml", temp_path)
            dockerfile_content = """
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
WORKDIR /app
COPY terminaide/ ./terminaide/
COPY terminarcade/ ./terminarcade/
COPY demo/ ./demo/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
CMD ["python", "demo/server.py", "apps"]
"""
            dockerfile_path = temp_path / "Dockerfile"
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)
            logger.info(f"Building Docker image: {image_name}")

            # Fix the build logs processing
            build_result = client.images.build(
                path=str(temp_path), tag=image_name, rm=True
            )

            # Unpack the build result properly
            image = build_result[0]
            build_logs = build_result[1]

            # Properly handle logs with explicit type checking
            for log in build_logs:
                if isinstance(log, dict) and "stream" in log:
                    stream_content = log.get("stream")
                    if isinstance(stream_content, str) and stream_content.strip():
                        logger.info(f"Build: {stream_content.strip()}")

            container_name = f"{image_name}-container"
            try:
                old_container = client.containers.get(container_name)
                old_container.stop()
                old_container.remove()
            except Exception as e:
                # Use dynamic error type checking
                NotFoundError = get_exception_class(docker_module, "NotFound")
                if not isinstance(e, NotFoundError):
                    logger.warning(f"Unexpected error when removing container: {e}")

            # Verify image.id is not None
            if not image or not image.id:
                logger.error("Invalid Docker image")
                return build_and_run_container_subprocess(port)

            logger.info(f"Starting container {container_name} on port {port}")

            # Fix: Use type casting to satisfy Pylance
            # Create a dictionary with the correct expected type
            ports_mapping = {f"8000/tcp": port}
            # Cast it to silence type errors
            ports_config: Dict[str, Union[int, List[int], Tuple[str, int], None]] = {
                "8000/tcp": port
            }

            # Make sure image.id is a string
            image_id = str(image.id)

            # Use explicit keyword arguments for the run method to satisfy type checking
            c = client.containers.run(
                image_id,
                name=container_name,
                ports=ports_config,
                detach=True,
                environment={"CONTAINER_MODE": "true"},
            )

            logger.info(f"Container {container_name} started (ID: {c.short_id})")
            logger.info(f"Access at: http://localhost:{port}")
            logger.info("Streaming container logs (Ctrl+C to stop)")
            try:
                for line in c.logs(stream=True):
                    if isinstance(line, bytes):
                        print(line.decode().strip())
            except KeyboardInterrupt:
                logger.info("Stopping container...")
                c.stop()
                logger.info("Container stopped")
    except Exception as e:
        logger.error(f"Error in container build/run: {e}")
        # Try subprocess approach as fallback
        logger.info("Falling back to subprocess implementation")
        build_and_run_container_subprocess(port)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # Add a single positional argument for mode
    parser.add_argument(
        "mode",
        nargs="?",
        default="default",
        choices=["default", "function", "script", "apps", "container"],
        help="Server mode to run",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Store the mode directly
    args.actual_mode = args.mode
    return args


def main() -> None:
    args = parse_args()
    mode = args.actual_mode
    port = args.port
    os.environ["TERMINAIDE_MODE"] = mode

    if mode != "container":
        os.environ["WATCHFILES_FORCE_POLLING"] = "0"
        os.environ["WATCHFILES_POLL_DELAY"] = "0.1"
        os.environ["TERMINAIDE_VERBOSE"] = "0"
        log_level = "WARNING" if mode != "apps" else "INFO"
        # Set terminaide logger level directly
        logger.setLevel(log_level)
        # Also set uvicorn logger level
        import logging

        logging.getLogger("uvicorn").setLevel(log_level)

    logger.info(f"Starting server in {mode.upper()} mode on port {port}")

    if mode == "container":
        build_and_run_container(port)
        return

    # DEFAULT MODE
    if mode == "default":
        serve_script(
            INSTRUCTIONS_PATH,
            port=port,
            title="Instructions",
            debug=True,
            reload=True,  # <-- Enable reload for default mode
        )
        return

    # FUNCTION MODE
    if mode == "function":
        serve_function(
            play_asteroids_function,
            port=port,
            title="Function Mode",
            debug=True,
            reload=True,  # <-- Enable reload for function mode
        )
        return

    # SCRIPT MODE
    if mode == "script":
        serve_script(
            CLIENT_SCRIPT,
            port=port,
            title="Script Mode",
            debug=True,
            reload=True,  # <-- Enable reload for script mode
        )
        return

    # APPS MODE
    if mode == "apps":
        logger.info(f"Visit http://localhost:{port} for the main interface")
        logger.info(f"Visit http://localhost:{port}/info for details")
        uvicorn.run(
            "demo.server:create_app",
            factory=True,
            host="0.0.0.0",
            port=port,
            reload=True,
            reload_dirs=[str(project_root)],
        )


if __name__ == "__main__":
    main()
