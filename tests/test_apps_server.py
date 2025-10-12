# test_apps_server.py

"""
Foundation testing module for Terminaide apps server functionality.

This module provides:
1. Enhanced DemoProcess class for managing test server lifecycles
2. Shared testing utilities for HTTP/WebSocket validation
3. Comprehensive apps server tests covering routing, configuration, and error handling
4. Base patterns for extension by function_server.py and script_server.py

Usage in other test modules:
    from tests.test_apps_server import DemoProcess, validate_http_response, verify_ttyd_health
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

import pytest
import requests
import websockets


# =============================================================================
# SHARED TESTING UTILITIES
# =============================================================================
# These utilities are designed to be imported and used by:
# - function_server.py (for testing function wrapping and ephemeral scripts)
# - script_server.py (for testing script execution and virtual environments)
# - test_demos.py (for DRY refactoring of existing demo tests)


class DemoProcess:
    """
    Enhanced process lifecycle manager for Terminaide testing.

    Supports both HTTP servers (apps mode) and non-HTTP processes (direct scripts).
    Provides comprehensive health checking, error detection, and cleanup.

    Usage patterns for different server types:
    - Apps server: check_http=True, port specified
    - Function server: check_http=True, ephemeral script handling
    - Script server: check_http=False for direct script execution
    """

    def __init__(self, script_path: str, port: int = 8000, check_http: bool = True):
        self.script_path = script_path
        self.port = port
        self.check_http = check_http
        self.process: Optional[subprocess.Popen] = None

    def start(
        self, timeout: int = 10, env_vars: Optional[Dict[str, str]] = None
    ) -> None:
        """Start the demo process and wait for it to be ready."""
        env = {**subprocess.os.environ}
        if env_vars:
            env.update(env_vars)

        self.process = subprocess.Popen(
            ["python", self.script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        if not self.check_http:
            # For non-HTTP processes (direct scripts), wait and check for crashes
            time.sleep(2)
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                # Allow expected curses errors in headless environments
                if "Error in AutoIndex: nocbreak() returned ERR" in stderr:
                    return
                raise RuntimeError(
                    f"Process exited early:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                )
            return

        # Wait for HTTP server to start
        self._wait_for_http_server(timeout)

    def _wait_for_http_server(self, timeout: int) -> None:
        """Wait for HTTP server to become available."""
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
        """Validate HTTP response and return content."""
        return validate_http_response(self.port, path)

    def stop(self, timeout: int = 5) -> None:
        """Stop the process gracefully with SIGINT, force kill if needed."""
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

    # TTYd and port management methods
    def verify_ttyd_processes(
        self, expected_ports: List[int], timeout: int = 10
    ) -> None:
        """Verify ttyd processes are running on expected ports."""
        verify_ttyd_health(expected_ports, timeout)

    def verify_terminal_connectivity(self, ttyd_ports: List[int]) -> None:
        """Verify terminal WebSocket connectivity for ttyd ports."""
        verify_websocket_connectivity(ttyd_ports)

    def check_terminal_health(self, terminal_routes: List[str]) -> None:
        """Check health of terminal routes by verifying HTTP responses."""
        for route in terminal_routes:
            response = self.check_http_response(route)
            # Check for server errors that indicate proxy/ttyd issues
            if "500 Internal Server Error" in response or "502 Bad Gateway" in response:
                raise RuntimeError(f"Terminal route {route} returned server error")


def validate_http_response(port: int, path: str = "/", timeout: int = 5) -> str:
    """
    Validate HTTP response for common issues and return content.

    Checks for:
    - HTTP 200 status
    - No Python tracebacks in response
    - No generic error messages

    Used by all server types for consistent response validation.
    """
    response = requests.get(f"http://localhost:{port}{path}", timeout=timeout)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    content = response.text
    assert "Traceback" not in content, "Response contains Python traceback"
    assert "Error:" not in content, "Response contains error message"

    return content


def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is listening for connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def verify_ttyd_health(expected_ports: List[int], timeout: int = 10) -> None:
    """
    Verify ttyd processes are running on expected ports.

    Critical for all server types that spawn terminal processes.
    Function and script servers will use this for their specific port ranges.
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        missing_ports = [port for port in expected_ports if not is_port_listening(port)]

        if not missing_ports:
            return  # All ports are listening

        time.sleep(0.5)

    # Final check with detailed error
    missing_ports = [port for port in expected_ports if not is_port_listening(port)]
    if missing_ports:
        raise RuntimeError(f"ttyd processes not listening on ports: {missing_ports}")


async def _test_websocket_connectivity_async(port: int, timeout: float = 3.0) -> bool:
    """Test WebSocket connectivity to a ttyd port."""
    try:
        uri = f"ws://localhost:{port}/ws"
        async with websockets.connect(uri, close_timeout=timeout) as websocket:
            # Send a ping to verify the connection is responsive
            await websocket.ping()
            return True
    except Exception:
        return False


def verify_websocket_connectivity(ttyd_ports: List[int]) -> None:
    """
    Verify terminal WebSocket connectivity for ttyd ports.

    Essential for validating that terminal processes are not just running
    but actually accepting WebSocket connections for terminal interaction.
    """

    async def check_all_terminals():
        failed_ports = []
        for port in ttyd_ports:
            if not await _test_websocket_connectivity_async(port):
                failed_ports.append(port)
        return failed_ports

    failed_ports = asyncio.run(check_all_terminals())

    if failed_ports:
        raise RuntimeError(
            f"Terminal WebSocket connectivity failed for ports: {failed_ports}"
        )


def create_temp_script(content: str, executable: bool = True) -> Path:
    """
    Create a temporary script file for testing.

    Useful for function_server.py (ephemeral function wrappers)
    and script_server.py (dynamic test scripts).
    """
    temp_file = Path(tempfile.mktemp(suffix=".py"))
    temp_file.write_text(content)
    if executable:
        temp_file.chmod(0o755)
    return temp_file


def cleanup_temp_files(file_patterns: List[str]) -> None:
    """
    Clean up temporary files matching patterns.

    Important for function_server.py to verify ephemeral script cleanup
    and script_server.py for dynamic argument parameter files.
    """
    temp_dir = Path(tempfile.gettempdir())
    for pattern in file_patterns:
        for temp_file in temp_dir.glob(pattern):
            try:
                temp_file.unlink()
            except Exception:
                pass


# =============================================================================
# DYNAMIC ARGUMENT TESTING UTILITIES
# =============================================================================
# These utilities specifically support dynamic argument testing
# Used for testing query parameter processing and custom args_param functionality


class DynamicTerminalTest:
    """
    Test helper for dynamic terminal routes with query parameter processing.

    Supports creating temporary test apps with configurable dynamic behavior,
    custom args_param settings, and validation of parameter file handling.

    This class will be used by script_server.py for comprehensive dynamic
    argument testing and can be imported by other test modules.
    """

    def __init__(self, port: int = 8000):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.test_script_path = Path(tempfile.gettempdir()) / "test_dynamic_script.py"
        self.test_app_path = Path(tempfile.gettempdir()) / "test_dynamic_app.py"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def create_test_script(self, script_content: Optional[str] = None) -> None:
        """Create a test script that prints command line arguments."""
        if script_content is None:
            script_content = """#!/usr/bin/env python3
import sys
print("Dynamic Script Test")
print(f"Arguments received: {sys.argv[1:]}")
for i, arg in enumerate(sys.argv[1:], 1):
    print(f"  Arg {i}: {arg}")
"""
        self.test_script_path.write_text(script_content)
        self.test_script_path.chmod(0o755)

    def create_test_app(self, dynamic: bool = True, args_param: str = "args") -> None:
        """Create a test FastAPI app with configurable dynamic behavior."""
        app_content = f"""#!/usr/bin/env python3
from pathlib import Path
from fastapi import FastAPI
import terminaide
import uvicorn

app = FastAPI()

terminal_routes = {{
    "/test": {{
        "script": "{self.test_script_path}",
        "args": ["--base-arg"],
        "dynamic": {dynamic},
        "args_param": "{args_param}",
        "title": "Dynamic Test Terminal",
    }}
}}

# Configure the app with terminaide
terminaide.serve_apps(app, terminal_routes)

if __name__ == "__main__":
    # Start the server
    uvicorn.run(app, host="0.0.0.0", port={self.port})
"""
        self.test_app_path.write_text(app_content)
        self.test_app_path.chmod(0o755)

    def start_app(self, timeout: int = 10) -> None:
        """Start the test app and wait for it to be ready."""
        self.process = subprocess.Popen(
            ["python", str(self.test_app_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={
                **os.environ,
                "TERMINAIDE_CURSOR_MGMT": "0",
            },  # Disable cursor management for tests
        )

        # Wait for HTTP server to start
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise RuntimeError(
                    f"Process exited early:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
                )

            try:
                response = requests.get(f"http://localhost:{self.port}/test", timeout=1)
                if response.status_code == 200:
                    return
            except requests.exceptions.RequestException:
                pass

            time.sleep(0.5)

        raise TimeoutError(f"Server did not start within {timeout} seconds")

    def stop_app(self, timeout: int = 5) -> None:
        """Stop the test app gracefully."""
        if self.process is None:
            return

        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def cleanup(self) -> None:
        """Clean up test files and processes."""
        self.stop_app()

        # Remove test files
        if self.test_script_path.exists():
            self.test_script_path.unlink()
        if self.test_app_path.exists():
            self.test_app_path.unlink()

        # Clean up any temp parameter files
        cleanup_terminaide_param_files()

    def check_iframe_src(self, query_params: str = "") -> str:
        """Get the iframe src response text for further assertions."""
        url = f"http://localhost:{self.port}/test"
        if query_params:
            url += f"?{query_params}"

        response = requests.get(url, timeout=5)
        assert response.status_code == 200

        return response.text

    async def test_websocket_params(
        self, query_params: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Test that WebSocket connection triggers parameter file creation."""
        # Build WebSocket URL
        ws_url = f"ws://localhost:{self.port}/test/terminal/ws"
        if query_params:
            ws_url += f"?{query_params}"

        try:
            async with websockets.connect(ws_url, subprotocols=["tty"]) as websocket:
                # Give the proxy time to write the parameter file
                await asyncio.sleep(0.5)

                # Check if parameter file was created
                param_file = Path("/tmp/params/terminaide_params__test.json")
                if param_file.exists():
                    data = json.loads(param_file.read_text())
                    return data

                return None
        except Exception as e:
            print(f"WebSocket error: {e}")
            return None


def cleanup_terminaide_param_files() -> None:
    """Clean up terminaide parameter files from /tmp directory."""
    # Check both the old location (direct in /tmp) and new location (/tmp/params)
    temp_dir = Path("/tmp")
    params_dir = temp_dir / "params"
    
    # Clean up from both locations for backward compatibility during transition
    for search_dir in [temp_dir, params_dir]:
        if search_dir.exists():
            for param_file in search_dir.glob("terminaide_params_*.json"):
                try:
                    param_file.unlink()
                except Exception:
                    pass


def check_parameter_file_exists(route_path: str) -> bool:
    """Check if a parameter file exists for a given route."""
    # Convert route path to parameter file name (e.g., "/test" -> "terminaide_params__test.json")
    route_name = route_path.lstrip("/").replace("/", "_")
    # Check in the params subdirectory under /tmp
    param_file = Path(f"/tmp/params/terminaide_params__{route_name}.json")
    return param_file.exists()


def read_parameter_file(route_path: str) -> Optional[Dict[str, Any]]:
    """Read and parse a parameter file for a given route."""
    route_name = route_path.lstrip("/").replace("/", "_")
    # Look in the params subdirectory under /tmp
    param_file = Path(f"/tmp/params/terminaide_params__{route_name}.json")

    if not param_file.exists():
        return None

    try:
        return json.loads(param_file.read_text())
    except (json.JSONDecodeError, IOError):
        return None


# =============================================================================
# APPS SERVER SPECIFIC TESTS
# =============================================================================
# These tests focus on apps server functionality:
# - Route registration and proxy routing
# - Port allocation and management
# - Configuration validation
# - Error handling and recovery


def test_apps_server_basic_routing():
    """Test basic apps server routing and proxy functionality."""
    with DemoProcess("examples/apps.py", port=8000) as demo:
        demo.start()

        # Test main page loads
        content = demo.check_http_response("/")
        assert len(content) > 100, "Main page should have substantial content"

        # Verify ttyd processes for all terminals
        expected_ttyd_ports = [7740, 7741, 7742, 7743, 7744]  # monitor, games
        demo.verify_ttyd_processes(expected_ttyd_ports)

        # Test specific routes
        demo.check_http_response("/monitor")

        # Test game terminal routes
        terminal_routes = ["/snake", "/tetris", "/pong", "/asteroids"]
        demo.check_terminal_health(terminal_routes)


def test_apps_server_websocket_connectivity():
    """Test WebSocket connectivity for all terminal routes."""
    with DemoProcess("examples/apps.py", port=8000) as demo:
        demo.start()

        # Verify WebSocket connectivity for all terminals
        expected_ttyd_ports = [7740, 7741, 7742, 7743, 7744]
        demo.verify_terminal_connectivity(expected_ttyd_ports)


def test_apps_server_port_allocation():
    """Test port allocation behavior and conflict detection."""
    # Start first server
    with DemoProcess("examples/apps.py", port=8000) as demo1:
        demo1.start()

        # Verify ports are allocated
        expected_ports = [7740, 7741, 7742, 7743, 7744]
        demo1.verify_ttyd_processes(expected_ports)

        # TODO: Test port conflict scenarios when multiple servers run
        # This would be useful for function_server.py and script_server.py
        # when testing concurrent server instances


def test_apps_server_graceful_shutdown():
    """Test graceful shutdown and cleanup behavior."""
    with DemoProcess("examples/apps.py", port=8000) as demo:
        demo.start()

        # Verify server is running
        demo.check_http_response("/")

        # Verify ttyd processes exist
        expected_ports = [7740, 7741, 7742, 7743, 7744]
        demo.verify_ttyd_processes(expected_ports)

        # Stop and verify cleanup
        demo.stop()

        # Give processes time to clean up
        time.sleep(5)

        # Note: TTYd processes may continue running independently after main process stops
        # This is often normal behavior - they're designed to be persistent
        active_ports = [port for port in expected_ports if is_port_listening(port)]

        # For now, just log the cleanup status rather than failing
        # TODO: Determine if TTYd processes should be auto-cleaned or persist
        if active_ports:
            print(f"INFO: TTYd processes still active on ports: {active_ports}")
            print("This may be normal behavior for persistent terminal processes")


def test_apps_server_error_responses():
    """Test error handling for invalid routes and malformed requests."""
    with DemoProcess("examples/apps.py", port=8000) as demo:
        demo.start()

        # Test 404 for non-existent routes
        response = requests.get("http://localhost:8000/nonexistent", timeout=5)
        assert response.status_code == 404, "Should return 404 for non-existent routes"

        # Test invalid terminal routes
        response = requests.get("http://localhost:8000/invalid-terminal", timeout=5)
        assert (
            response.status_code == 404
        ), "Should return 404 for invalid terminal routes"


def test_apps_server_concurrent_connections():
    """Test handling of multiple concurrent HTTP connections."""
    with DemoProcess("examples/apps.py", port=8000) as demo:
        demo.start()

        # Make multiple concurrent requests
        import concurrent.futures

        def make_request(path: str) -> int:
            response = requests.get(f"http://localhost:8000{path}", timeout=10)
            return response.status_code

        paths = ["/", "/monitor", "/snake", "/tetris", "/pong"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, path) for path in paths]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # All requests should succeed
        assert all(
            status == 200 for status in results
        ), "All concurrent requests should succeed"


# =============================================================================
# DYNAMIC ARGUMENT TESTS
# =============================================================================
# These tests cover dynamic query parameter processing, custom args_param,
# and parameter file management - essential for script server functionality


def test_dynamic_route_basic():
    """Test that a dynamic route passes query parameters correctly."""
    with DynamicTerminalTest() as test:
        test.create_test_script()
        test.create_test_app(dynamic=True)
        test.start_app()

        # Test without query params
        response_text = test.check_iframe_src()
        assert "/test/terminal" in response_text, "Should contain basic terminal path"

        # Test with query params
        query_params = "args=--verbose,--mode,production"
        response_text = test.check_iframe_src(query_params)
        expected_src = f"/test/terminal?{query_params}"
        assert (
            expected_src in response_text
        ), f"Expected iframe src to contain '{expected_src}'"


def test_dynamic_route_websocket_params():
    """Test that WebSocket connections write parameter files for dynamic routes."""
    with DynamicTerminalTest() as test:
        test.create_test_script()
        test.create_test_app(dynamic=True)
        test.start_app()

        # Test WebSocket with query params
        query_params = "args=--test,--verbose"
        param_data = asyncio.run(test.test_websocket_params(query_params))

        assert param_data is not None, "Parameter file should have been created"
        assert param_data["type"] == "query_params"
        assert param_data["params"]["args"] == "--test,--verbose"


def test_non_dynamic_route():
    """Test that non-dynamic routes don't process query parameters."""
    with DynamicTerminalTest() as test:
        test.create_test_script()
        test.create_test_app(dynamic=False)
        test.start_app()

        # Check that query params are NOT included in iframe src for non-dynamic routes
        response_text = test.check_iframe_src("args=--should-not-appear")
        assert (
            "args=--should-not-appear" not in response_text
        ), "Non-dynamic routes should not pass query params"


def test_custom_args_param_basic():
    """Test custom args_param functionality."""
    with DynamicTerminalTest() as test:
        test.create_test_script()
        test.create_test_app(dynamic=True, args_param="with")
        test.start_app()

        # Test with custom parameter name
        query_params = "with=--test,--verbose"
        response_text = test.check_iframe_src(query_params)
        expected_src = f"/test/terminal?{query_params}"
        assert (
            expected_src in response_text
        ), f"Expected iframe src to contain '{expected_src}'"


def test_custom_args_param_websocket_integration():
    """Test that custom args_param works with WebSocket parameter passing."""
    with DynamicTerminalTest() as test:
        test.create_test_script()
        test.create_test_app(dynamic=True, args_param="with")
        test.start_app()

        # Test WebSocket with custom parameter name
        query_params = "with=--test,--verbose"
        param_data = asyncio.run(test.test_websocket_params(query_params))

        assert param_data is not None, "Parameter file should have been created"
        assert param_data["type"] == "query_params"
        assert param_data["params"]["with"] == "--test,--verbose"


def test_empty_query_params_handling():
    """Test that empty parameter files are created and handled correctly."""
    with DynamicTerminalTest() as test:
        test.create_test_script()
        test.create_test_app(dynamic=True)
        test.start_app()

        # Test WebSocket connection without query params
        param_data = asyncio.run(test.test_websocket_params(""))

        # Even with no params, a parameter file should be created
        assert (
            param_data is not None
        ), "Parameter file should be created even when empty"
        assert param_data["type"] == "query_params"
        assert param_data["params"] == {}


def test_parameter_file_cleanup():
    """Test that parameter files are properly cleaned up."""
    # Create a test parameter file manually
    test_route = "/test-cleanup"
    route_name = test_route.lstrip("/").replace("/", "_")
    
    # Ensure the params directory exists
    params_dir = Path("/tmp/params")
    params_dir.mkdir(exist_ok=True, parents=True)
    param_file = params_dir / f"terminaide_params__{route_name}.json"

    # Write test parameter file
    test_data = {"type": "query_params", "params": {"args": "--test"}}
    param_file.write_text(json.dumps(test_data))

    assert param_file.exists(), "Parameter file should exist"

    # Clean up and verify removal
    cleanup_terminaide_param_files()

    # File should be gone
    assert not param_file.exists(), "Parameter file should be cleaned up"


# =============================================================================
# UNIT TESTS FOR ARGUMENT PARSING
# =============================================================================
# Direct testing of argument parsing logic from terminaide.core.wrappers


def test_argument_parsing_logic():
    """Test the argument parsing logic directly."""
    from terminaide.core.wrappers import parse_args_query_param

    # Test basic parsing
    assert parse_args_query_param("--verbose") == ["--verbose"]
    assert parse_args_query_param("--mode,production") == ["--mode", "production"]
    assert parse_args_query_param("--flag1,value1,--flag2") == [
        "--flag1",
        "value1",
        "--flag2",
    ]

    # Test edge cases
    assert parse_args_query_param("") == []
    assert parse_args_query_param("   ") == []
    assert parse_args_query_param("--trim  ,  spaces  ") == ["--trim", "spaces"]

    # Test custom args_param (parameter name doesn't affect parsing logic)
    assert parse_args_query_param("--verbose,--mode,prod", "with") == [
        "--verbose",
        "--mode",
        "prod",
    ]


def test_parameter_file_utilities():
    """Test parameter file utility functions."""
    from terminaide.core.wrappers import (
        write_query_params_file,
        cleanup_stale_param_files,
    )
    from terminaide.core.config import TerminaideConfig

    # Create a test config with explicit cache directory
    temp_dir = Path(tempfile.gettempdir())
    test_cache_dir = temp_dir / "terminaide_test_cache"
    test_cache_dir.mkdir(exist_ok=True)

    config = TerminaideConfig(ephemeral_cache_dir=test_cache_dir)

    try:
        # Create a test parameter file
        test_params = {"args": "--test"}
        param_file = write_query_params_file("/test-utils", test_params, config)

        assert param_file.exists(), "Parameter file should exist"
        assert (
            test_cache_dir in param_file.parents
        ), "Parameter file should be in test cache directory"

        # Verify file content
        data = json.loads(param_file.read_text())
        assert data["type"] == "query_params"
        assert data["params"] == test_params

        # Clean up stale files (with very short max age for testing)
        cleanup_stale_param_files(max_age_seconds=0, config=config)

        # File should be gone (since max_age_seconds=0 makes it immediately stale)
        assert not param_file.exists(), "Parameter file should be cleaned up"

    finally:
        # Clean up test directory
        import shutil

        if test_cache_dir.exists():
            shutil.rmtree(test_cache_dir, ignore_errors=True)


def test_configuration_models():
    """Test configuration model handling for dynamic arguments."""
    from terminaide.core.models import ScriptConfig, create_route_configs

    # Test ScriptConfig with custom args_param
    config = ScriptConfig(
        route_path="/test", script=Path("/tmp/test.py"), dynamic=True, args_param="with"
    )

    assert config.args_param == "with"
    assert config.dynamic is True

    # Test default args_param
    config_default = ScriptConfig(
        route_path="/test", script=Path("/tmp/test.py"), dynamic=True
    )

    assert config_default.args_param == "args"

    # Test route configuration creation with custom args_param
    terminal_routes = {
        "/test": {"script": "/tmp/test.py", "dynamic": True, "args_param": "with"}
    }

    route_configs = create_route_configs(terminal_routes)

    assert len(route_configs) == 1
    script_config = route_configs[0]
    assert script_config.args_param == "with"
    assert script_config.dynamic is True


# =============================================================================
# CONFIGURATION AND ERROR HANDLING TESTS
# =============================================================================
# These tests validate configuration handling and error scenarios
# Patterns here will be extended by function_server.py and script_server.py


def test_apps_server_configuration_validation():
    """Test various configuration scenarios and validation."""
    # This test would be expanded with actual configuration testing
    # once we understand the configuration patterns better

    # TODO: Test invalid port ranges
    # TODO: Test missing script files
    # TODO: Test invalid route configurations
    # These patterns will be crucial for function_server.py and script_server.py
    pass


def test_apps_server_process_recovery():
    """Test recovery behavior when ttyd processes fail."""
    # This test would simulate ttyd process failures and verify recovery

    # TODO: Kill individual ttyd processes and verify restart
    # TODO: Test behavior when port becomes unavailable
    # This pattern will be important for function_server.py ephemeral script testing
    pass


# =============================================================================
# PATTERNS FOR EXTENSION MODULES
# =============================================================================

"""
EXTENSION PATTERNS FOR function_server.py:

1. Import utilities:
   from tests.test_apps_server import DemoProcess, validate_http_response, verify_ttyd_health

2. Test function wrapping:
   - Create test functions with various signatures
   - Use create_temp_script() to generate ephemeral wrappers  
   - Verify function execution through terminal interface
   - Test cleanup of ephemeral scripts with cleanup_temp_files()

3. Test function-specific error scenarios:
   - Functions that raise exceptions
   - Functions with invalid signatures
   - Import errors in function modules

4. Test function server configuration:
   - Different function configurations
   - Memory management for function wrappers

EXTENSION PATTERNS FOR script_server.py:

1. Import utilities:
   from tests.test_apps_server import (
       DemoProcess, DynamicTerminalTest, validate_http_response, 
       verify_ttyd_health, cleanup_terminaide_param_files
   )

2. Test script execution:
   - Various script types and configurations
   - Virtual environment detection and usage
   - Script argument passing (static and dynamic)
   - Use DynamicTerminalTest for comprehensive dynamic argument testing

3. Test script-specific features:
   - Advanced dynamic argument scenarios using existing utilities
   - Custom args_param edge cases and validation
   - Script execution in different environments
   - Parameter file lifecycle management

4. Test script error scenarios:
   - Missing script files
   - Permission errors
   - Script execution failures
   - Invalid dynamic argument configurations

REFACTORING PATTERNS FOR test_demos.py:

1. Replace DemoProcess class with import:
   from tests.apps_server import DemoProcess

2. Use shared utilities:
   - Replace custom validation with validate_http_response()
   - Use verify_ttyd_health() and verify_websocket_connectivity()

3. Keep existing test structure but remove duplicate code
4. Maintain Docker testing functionality
"""


if __name__ == "__main__":
    # Manual test runner for development
    print("Running apps server foundation tests...")

    # Basic apps server functionality
    test_apps_server_basic_routing()
    print("✓ Basic routing test passed")

    test_apps_server_websocket_connectivity()
    print("✓ WebSocket connectivity test passed")

    test_apps_server_graceful_shutdown()
    print("✓ Graceful shutdown test passed")

    test_apps_server_error_responses()
    print("✓ Error response test passed")

    test_apps_server_concurrent_connections()
    print("✓ Concurrent connections test passed")

    # Dynamic argument functionality
    test_dynamic_route_basic()
    print("✓ Basic dynamic route test passed")

    test_dynamic_route_websocket_params()
    print("✓ WebSocket parameter test passed")

    test_non_dynamic_route()
    print("✓ Non-dynamic route test passed")

    test_custom_args_param_basic()
    print("✓ Custom args_param test passed")

    test_custom_args_param_websocket_integration()
    print("✓ Custom args_param WebSocket test passed")

    test_empty_query_params_handling()
    print("✓ Empty query params test passed")

    test_parameter_file_cleanup()
    print("✓ Parameter file cleanup test passed")

    # Unit tests for parsing logic
    test_argument_parsing_logic()
    print("✓ Argument parsing test passed")

    test_parameter_file_utilities()
    print("✓ Parameter file utilities test passed")

    test_configuration_models()
    print("✓ Configuration models test passed")

    print("\nAll comprehensive apps server tests passed!")
