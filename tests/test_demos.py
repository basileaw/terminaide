#!/usr/bin/env python3
"""
Simple tests for Terminaide demo modes.

Tests verify that each demo can start successfully, serve HTTP responses without
Python tracebacks, and shut down cleanly.
"""

import asyncio
import signal
import socket
import subprocess
import time
from typing import Optional, List

import pytest
import requests
import websockets

# Note: This test file may produce some harmless pytest warnings about:
# - Unknown mark 'docker' (the marker works correctly)
# - Asyncio fixture loop scope (using defaults is fine)
# These don't affect test functionality and can be safely ignored.


class DemoProcess:
    """Helper class to manage demo process lifecycle."""

    def __init__(self, script_path: str, port: int = 8000, check_http: bool = True):
        self.script_path = script_path
        self.port = port
        self.check_http = check_http
        self.process: Optional[subprocess.Popen] = None

    def start(self, timeout: int = 10) -> None:
        """Start the demo process and wait for it to be ready."""
        self.process = subprocess.Popen(
            ["python", self.script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if not self.check_http:
            # For non-HTTP demos (like script.py), just wait a bit and check it didn't crash
            time.sleep(2)
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                if "Error in AutoIndex: nocbreak() returned ERR" in stderr:
                    # This is expected for curses apps in headless environments
                    return
                raise RuntimeError(
                    f"Process exited early:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                )
            return

        # Wait for HTTP server to start
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise RuntimeError(
                    f"Process exited early:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                )

            try:
                response = requests.get(f"http://localhost:{self.port}", timeout=1)
                if response.status_code == 200:
                    return
            except requests.exceptions.RequestException:
                pass

            time.sleep(0.5)

        raise TimeoutError(f"Server did not start within {timeout} seconds")

    def check_http_response(self, path: str = "/") -> str:
        """Check HTTP response and return content."""
        response = requests.get(f"http://localhost:{self.port}{path}", timeout=5)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        content = response.text
        assert "Traceback" not in content, "Response contains Python traceback"
        assert "Error:" not in content, "Response contains error message"

        return content

    def stop(self, timeout: int = 5) -> None:
        """Stop the demo process gracefully."""
        if self.process is None:
            return

        # Send SIGINT for graceful shutdown
        self.process.send_signal(signal.SIGINT)

        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Force kill if graceful shutdown fails
            self.process.kill()
            self.process.wait()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False  # Don't suppress exceptions

    def _is_port_listening(self, port: int, host: str = "127.0.0.1") -> bool:
        """Check if a port is listening for connections."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                return result == 0
        except Exception:
            return False

    def verify_ttyd_processes(
        self, expected_ports: List[int], timeout: int = 10
    ) -> None:
        """Verify ttyd processes are running on expected ports."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            missing_ports = []
            for port in expected_ports:
                if not self._is_port_listening(port):
                    missing_ports.append(port)

            if not missing_ports:
                return  # All ports are listening

            time.sleep(0.5)

        # Final check with detailed error
        missing_ports = [
            port for port in expected_ports if not self._is_port_listening(port)
        ]
        if missing_ports:
            raise RuntimeError(
                f"ttyd processes not listening on ports: {missing_ports}"
            )

    def check_terminal_health(self, terminal_routes: List[str]) -> None:
        """Check health of terminal routes by verifying their ttyd processes."""
        for route in terminal_routes:
            response = self.check_http_response(route)
            # Basic check that the page loaded and isn't showing obvious errors
            if "500 Internal Server Error" in response or "502 Bad Gateway" in response:
                raise RuntimeError(f"Terminal route {route} returned server error")

    async def _test_websocket_connectivity(
        self, port: int, timeout: float = 3.0
    ) -> bool:
        """Test WebSocket connectivity to a ttyd port."""
        try:
            uri = f"ws://localhost:{port}/ws"
            async with websockets.connect(uri, close_timeout=timeout) as websocket:
                # Send a simple ping to verify the connection is responsive
                await websocket.ping()
                return True
        except Exception:
            return False

    def verify_terminal_connectivity(self, ttyd_ports: List[int]) -> None:
        """Verify terminal WebSocket connectivity for ttyd ports."""

        async def check_all_terminals():
            failed_ports = []
            for port in ttyd_ports:
                if not await self._test_websocket_connectivity(port):
                    failed_ports.append(port)
            return failed_ports

        # Run the async connectivity check
        failed_ports = asyncio.run(check_all_terminals())

        if failed_ports:
            raise RuntimeError(
                f"Terminal WebSocket connectivity failed for ports: {failed_ports}"
            )




def test_serve_function():
    """Test: python examples/function.py starts and responds."""
    with DemoProcess("examples/function.py", port=8000) as demo:
        demo.start()

        # Verify ttyd process is running for the terminal
        demo.verify_ttyd_processes([7740])

        # Verify terminal WebSocket connectivity
        demo.verify_terminal_connectivity([7740])

        # Test HTTP response
        content = demo.check_http_response()
        assert len(content) > 100, "Response should have substantial content"


def test_serve_script():
    """Test: python examples/script.py starts and responds."""
    # Script mode now uses serve_script() which creates an HTTP server
    with DemoProcess("examples/script.py", port=8000) as demo:
        demo.start()
        
        # Verify ttyd process is running for the terminal
        demo.verify_ttyd_processes([7740])
        
        # Verify terminal WebSocket connectivity
        demo.verify_terminal_connectivity([7740])
        
        # Test HTTP response
        content = demo.check_http_response()
        assert len(content) > 100, "Response should have substantial content"


def test_serve_apps():
    """Test: python examples/apps.py starts and all routes respond."""
    with DemoProcess("examples/apps.py", port=8000) as demo:
        demo.start()

        # Test main page
        demo.check_http_response("/")

        # Verify ttyd processes are running for all terminals
        # Apps mode allocates ports starting from 7740
        expected_ttyd_ports = [
            7740,
            7741,
            7742,
            7743,
            7744,
        ]  # monitor, snake, tetris, pong, asteroids
        demo.verify_ttyd_processes(expected_ttyd_ports)

        # Verify terminal WebSocket connectivity for all terminals
        demo.verify_terminal_connectivity(expected_ttyd_ports)

        # Test monitor page
        demo.check_http_response("/monitor")

        # Test game routes with terminal health verification
        terminal_routes = ["snake", "tetris", "pong", "asteroids"]
        demo.check_terminal_health([f"/{route}" for route in terminal_routes])


def test_serve_container():
    """Test: make spin builds Docker image and runs container (requires Docker)."""
    # Skip if Docker not available
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available")

    # Clean up any existing container first
    try:
        subprocess.run(["docker", "stop", "terminaide-container"], capture_output=True, timeout=5)
        subprocess.run(["docker", "rm", "terminaide-container"], capture_output=True, timeout=5)
    except:
        pass

    # Test make spin command - it builds and runs container
    process = subprocess.Popen(
        ["make", "spin"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for build and startup process
        time.sleep(10)

        # Check if process is still running (container should be running)
        if process.poll() is None:
            # Still running - container is likely running successfully
            # Verify container is actually running
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=terminaide-container", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            assert "terminaide-container" in result.stdout, "Container is not running"

            # Wait for HTTP server to be ready (container needs time to install deps and start)
            max_wait = 30  # seconds
            start_time = time.time()
            while time.time() - start_time < max_wait:
                try:
                    response = requests.get("http://localhost:8000", timeout=2)
                    if response.status_code == 200:
                        break  # Server is ready
                except requests.exceptions.RequestException:
                    time.sleep(2)  # Wait before retrying
            else:
                # If we get here, server didn't start in time
                raise RuntimeError(f"Container HTTP server did not start within {max_wait} seconds")

        else:
            # Process completed - check for errors
            stdout, stderr = process.communicate()
            if "Error" in stderr or process.returncode != 0:
                raise RuntimeError(f"make spin failed:\nSTDOUT: {stdout}\nSTDERR: {stderr}")

    finally:
        # Clean up: kill process and containers
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

        # Clean up container
        try:
            subprocess.run(["docker", "stop", "terminaide-container"], capture_output=True, timeout=10)
            subprocess.run(["docker", "rm", "terminaide-container"], capture_output=True, timeout=10)
        except:
            pass
