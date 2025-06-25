#!/usr/bin/env python3
"""
Standalone demo of running terminaide in a Docker container.

This example shows how to build and run the terminaide demo in Docker.

Usage:
    python tryit/container.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Union

from terminaide import logger


def generate_requirements_txt(pyproject_path: Path, temp_dir: Union[str, Path]) -> Path:
    """Generate requirements.txt from pyproject.toml dependencies (excludes dev deps)."""
    try:
        logger.info("Generating requirements.txt (excluding tryit)")
        req_path = Path(temp_dir) / "requirements.txt"

        # Read pyproject.toml
        with open(pyproject_path, "r") as f:
            content = f.read()

        # Find the main dependencies section
        deps_section = re.search(
            r"\[tool\.poetry\.dependencies\](.*?)(?=\n\[|$)",
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


def build_and_run_container(port: int = 8000) -> None:
    """Build and run the application in a Docker container.

    Args:
        port: Host port to expose (container always uses 8000 internally)
    """
    # Set up logging with terminaide formatter
    from terminaide.core.logger import setup_package_logging

    setup_package_logging(configure=True)

    # Check if docker is installed
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("Docker is not installed or not in PATH")
        sys.exit(1)

    project_root = Path(__file__).parent.parent.absolute()
    image_name = project_root.name.lower()

    # Create temp directory and generate files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        # Copy directories
        for directory in ["terminaide", "terminarcade", "tryit"]:
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

        # Generate requirements
        generate_requirements_txt(project_root / "pyproject.toml", temp_path)

        # Create Dockerfile
        dockerfile_content = """FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
WORKDIR /app
COPY terminaide/ ./terminaide/
COPY terminarcade/ ./terminarcade/
COPY tryit/ ./tryit/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
CMD ["python", "tryit/apps.py"]
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
        logger.info(f"Server Logs:\nhttp://localhost:{port}/monitor")
        logger.info("Streaming container logs (Ctrl+C to stop)")

        try:
            # Stream logs
            log_cmd = ["docker", "logs", "-f", container_id]
            subprocess.run(log_cmd)
        except KeyboardInterrupt:
            logger.info("Stopping container...")
            subprocess.run(["docker", "stop", container_id], capture_output=True)
            logger.info("Container stopped")


if __name__ == "__main__":
    build_and_run_container()
