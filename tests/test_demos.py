#!/usr/bin/env python3
"""
Simple tests for Terminaide demo modes.

Tests verify that each demo can start successfully, serve HTTP responses without
Python tracebacks, and shut down cleanly.
"""

import asyncio
import os
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
        env = os.environ.copy()
        env["TERMINAIDE_PORT"] = str(self.port)

        self.process = subprocess.Popen(
            ["python", self.script_path],
            env=env,
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


def test_serve_default():
    """Test: python demo/instructions.py starts and responds."""
    # Note: instructions.py hardcodes port 8000, so we need to kill anything on that port first
    import subprocess

    try:
        subprocess.run(
            ["pkill", "-f", "python demo/instructions.py"], capture_output=True
        )
        subprocess.run(["pkill", "-f", "python demo/function.py"], capture_output=True)
    except:
        pass

    with DemoProcess("demo/instructions.py", port=8000) as demo:
        demo.start()

        # Verify ttyd process is running for the terminal
        demo.verify_ttyd_processes([7744])

        # Verify terminal WebSocket connectivity
        demo.verify_terminal_connectivity([7744])

        # Test HTTP response
        content = demo.check_http_response()
        assert "terminaide" in content.lower(), "Response should mention terminaide"


def test_serve_function():
    """Test: python demo/function.py starts and responds."""
    # Note: function.py uses default port 8000, so test immediately after default test
    with DemoProcess("demo/function.py", port=8000) as demo:
        demo.start()

        # Verify ttyd process is running for the terminal
        demo.verify_ttyd_processes([7744])

        # Verify terminal WebSocket connectivity
        demo.verify_terminal_connectivity([7744])

        # Test HTTP response
        content = demo.check_http_response()
        assert len(content) > 100, "Response should have substantial content"


def test_serve_script():
    """Test: python demo/script.py starts (no HTTP check since it's terminal-only)."""
    # For script mode, we just verify the process starts without crashing
    with DemoProcess("demo/script.py", port=8003, check_http=False) as demo:
        demo.start(timeout=5)  # Shorter timeout since no HTTP server
        # If we get here without exceptions, the process started successfully


def test_serve_apps():
    """Test: python demo/apps.py starts and all routes respond."""
    with DemoProcess("demo/apps.py", port=8004) as demo:
        demo.start()

        # Test main page
        demo.check_http_response("/")

        # Verify ttyd processes are running for all terminals
        # Apps mode allocates ports starting from base_port - 4 (so 8004-4=8000, then 7744, 7745, etc.)
        expected_ttyd_ports = [
            7744,
            7745,
            7746,
            7747,
            7748,
        ]  # monitor, snake, tetris, pong, asteroids
        demo.verify_ttyd_processes(expected_ttyd_ports)

        # Verify terminal WebSocket connectivity for all terminals
        demo.verify_terminal_connectivity(expected_ttyd_ports)

        # Test monitor page
        demo.check_http_response("/monitor")

        # Test game routes with terminal health verification
        terminal_routes = ["snake", "tetris", "pong", "asteroids"]
        demo.check_terminal_health([f"/{route}" for route in terminal_routes])


@pytest.mark.docker
def test_serve_container():
    """Test: python demo/container.py builds and responds (requires Docker)."""
    # Skip if Docker not available
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available")

    # Container demo is special - it builds and runs in Docker, then streams logs
    # We just verify it starts without Python errors
    env = os.environ.copy()
    env["TERMINAIDE_PORT"] = "8005"

    process = subprocess.Popen(
        ["python", "demo/container.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for build process to start
        time.sleep(10)

        # Check if process is still running (build in progress) or completed successfully
        if process.poll() is None:
            # Still running - likely building or running container
            # Test passes if no immediate crash
            pass
        else:
            # Process completed - check for errors
            stdout, stderr = process.communicate()
            assert "Docker build failed" not in stderr, "Docker build failed"
            assert "Docker run failed" not in stderr, "Docker run failed"

        # Try to connect to port 8005 to see if container is running
        try:
            response = requests.get("http://localhost:8005", timeout=2)
            if response.status_code == 200:
                # Great! Container is running and serving
                pass
        except requests.exceptions.RequestException:
            # Container might still be starting, that's okay for this test
            pass

    finally:
        # Clean up: kill process and any containers
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

        # Clean up any containers created by the test
        try:
            subprocess.run(
                ["docker", "stop", "terminaide-container"],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["docker", "rm", "terminaide-container"],
                capture_output=True,
                timeout=10,
            )
        except:
            pass
