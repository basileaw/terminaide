# tests/container.py

"""
Script to build and run terminaide in a container using the Docker SDK.
This replaces the need for a separate Dockerfile and manual docker commands.
"""

import logging
import re
import shutil
import sys
import tempfile
from pathlib import Path

import docker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:     %(name)s - %(message)s"
)

logger = logging.getLogger(__name__)

def extract_dependencies_from_pyproject(pyproject_path):
    """
    Extract dependencies from pyproject.toml file.
    
    Args:
        pyproject_path: Path to pyproject.toml file
        
    Returns:
        list: List of dependencies in pip format
    """
    try:
        with open(pyproject_path, "r") as f:
            content = f.read()
        
        # Extract dependencies section using regex
        deps_match = re.search(r'\[tool\.poetry\.dependencies\]([\s\S]*?)(\[tool|$)', content)
        if not deps_match:
            raise ValueError("Could not find dependencies section in pyproject.toml")
        
        deps_section = deps_match.group(1)
        package_matches = re.findall(r'(\w+)\s*=\s*["\']([^"\']+)["\']', deps_section)
        
        dependencies = []
        for package, version in package_matches:
            if package != "python":  # Skip python version constraint
                if version.startswith("^") or version.startswith("~"):
                    # Convert Poetry version specifiers to pip format
                    version = ">=" + version[1:]
                dependencies.append(f"{package}{version}")
        
        return dependencies
        
    except Exception as e:
        logger.error(f"Failed to extract dependencies: {e}")
        # Return fallback dependencies
        return ["fastapi", "uvicorn", "httpx", "websockets", "jinja2"]

def build_and_run_container(port=8000):
    """
    Build Docker image and run container using Docker SDK.
    
    Args:
        port: Port to expose from the container
    """
    try:
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
            logger.info("Generating requirements.txt from pyproject.toml")
            dependencies = extract_dependencies_from_pyproject(project_root / "pyproject.toml")
            
            # Write dependencies to requirements.txt
            req_path = temp_path / "requirements.txt"
            with open(req_path, "w") as f:
                for dep in dependencies:
                    f.write(f"{dep}\n")
            
            # Create Dockerfile in the temporary directory
            dockerfile_content = """FROM python:3.12-slim

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

CMD ["python", "tests/server.py"]
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
        
    except docker.errors.DockerException as e:
        logger.error(f"Docker error: {e}")
        logger.error("Make sure Docker is installed and running")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Parse port from command line args if provided
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            logger.error(f"Invalid port number: {sys.argv[1]}")
            sys.exit(1)
    
    try:
        build_and_run_container(port=port)
    except KeyboardInterrupt:
        logger.info("\nScript interrupted by user, exiting...")
        sys.exit(0)