#!/usr/bin/env python3

import os
import sys
import json
import tempfile
import shutil
import subprocess
from pathlib import Path

import docker

"""
test_middleware.py

This script demonstrates a local end-to-end test of Terminaide's
proxy header middleware in a Docker container, using the Docker
Python library. It:

1. Creates an ephemeral directory with:
   - A minimal Dockerfile
   - A minimal server.py that uses Terminaide

2. Builds a Docker image (copying local terminaide source)
3. Runs the container, streams logs
4. Checks for the "Added proxy header middleware for HTTPS detection" line
   in the container logs
5. Stops the container and prints PASS/FAIL accordingly

To run:
    python test_middleware.py

Passing condition:
    The container logs must contain:
    "Added proxy header middleware for HTTPS detection"
"""

IMAGE_NAME = "terminaide-middleware-test"
CONTAINER_NAME = "terminaide-middleware-container"

SERVER_PY_CONTENT = r'''\
from terminaide import serve_function

def main():
    print("Hello from the test script!")
    input("Press ENTER to exit...")

if __name__ == "__main__":
    # We expect to see the proxy middleware line in the logs if
    # trust_proxy_headers is working in serve_function's container usage
    serve_function(main, title="Test Middleware")
'''

DOCKERFILE_CONTENT = r'''\
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir poetry

# Copy local Terminaide config
COPY pyproject.toml poetry.lock* ./

# Install dependencies, excluding dev extras
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main --no-root

# Copy the local terminaide source code into the container
COPY terminaide ./terminaide

# Copy the ephemeral server.py
COPY server.py ./server.py

EXPOSE 8000
ENTRYPOINT ["python", "-u", "server.py"]
'''

def main():
    client = None
    temp_dir = None

    try:
        # Step 1: Create ephemeral directory
        temp_dir = Path(tempfile.mkdtemp(prefix="terminaide_middleware_test_"))

        # Write server.py
        (temp_dir / "server.py").write_text(SERVER_PY_CONTENT, encoding="utf-8")

        # Write Dockerfile
        (temp_dir / "Dockerfile").write_text(DOCKERFILE_CONTENT, encoding="utf-8")

        # Copy local pyproject + poetry.lock if they exist
        repo_root = Path(__file__).parent.parent.absolute()
        pyproject_src = repo_root / "pyproject.toml"
        poetry_lock_src = repo_root / "poetry.lock"
        if pyproject_src.exists():
            shutil.copy2(pyproject_src, temp_dir / "pyproject.toml")
        if poetry_lock_src.exists():
            shutil.copy2(poetry_lock_src, temp_dir / "poetry.lock")

        # Copy terminaide source directory
        terminaide_src = repo_root / "terminaide"
        terminaide_dst = temp_dir / "terminaide"
        shutil.copytree(terminaide_src, terminaide_dst)

        print(f"[INFO] Temp directory created at: {temp_dir}")

        # Step 2: Docker client
        context_result = subprocess.run(["docker", "context", "inspect"], capture_output=True, text=True)
        if context_result.returncode == 0:
            context_data = json.loads(context_result.stdout)
            docker_host = context_data[0]["Endpoints"]["docker"]["Host"]
            client = docker.DockerClient(base_url=docker_host)
        else:
            client = docker.from_env()

        client.ping()  # simple test

        # Step 3: Build image
        print(f"[INFO] Building Docker image {IMAGE_NAME}...")
        image, build_logs = client.images.build(
            path=str(temp_dir),
            tag=IMAGE_NAME,
            rm=True
        )
        for log_line in build_logs:
            if "stream" in log_line:
                line = log_line["stream"].strip()
                if line:
                    print(f"  {line}")

        # Remove existing container if it exists
        try:
            old_container = client.containers.get(CONTAINER_NAME)
            old_container.stop()
            old_container.remove()
        except docker.errors.NotFound:
            pass

        # Step 4: Run container
        print(f"[INFO] Starting container {CONTAINER_NAME} from image {IMAGE_NAME} on port 8000...")
        container = client.containers.run(
            IMAGE_NAME,
            name=CONTAINER_NAME,
            ports={"8000/tcp": 8000},
            detach=True
        )

        print("[INFO] Container started. Streaming logs...")

        # Step 5: Monitor logs, look for the success line
        pass_line = "Added proxy header middleware for HTTPS detection"
        found_line = False
        try:
            for log in container.logs(stream=True):
                line_text = log.decode("utf-8", errors="ignore").strip()
                print(line_text)
                if pass_line in line_text:
                    found_line = True
                    print("[INFO] Found success line in container logs!")
                    break
        except KeyboardInterrupt:
            pass

        # Step 6: Stop container
        print("[INFO] Stopping container...")
        container.stop()
        container.remove()

        if found_line:
            print("TEST PASSED: Found proxy header middleware log entry.")
            sys.exit(0)
        else:
            print("TEST FAILED: Did NOT find the proxy header middleware log entry.")
            sys.exit(1)

    except Exception as e:
        print(f"[ERROR] Test encountered an exception: {e}")
        sys.exit(1)
    finally:
        # Cleanup temp directory
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
