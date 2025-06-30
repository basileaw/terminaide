# test_dynamic_args.py
"""
Tests for the dynamic query arguments feature in Terminaide.

These tests verify that routes with dynamic=True can accept query parameters
that are passed to the underlying scripts.
"""

import os
import json
import time
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

import pytest
import requests
import asyncio
import websockets


class DynamicTerminalTest:
    """Test helper for dynamic terminal routes."""
    
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
        
    def create_test_script(self):
        """Create a test script that prints command line arguments."""
        script_content = '''#!/usr/bin/env python3
import sys
print("Dynamic Script Test")
print(f"Arguments received: {sys.argv[1:]}")
for i, arg in enumerate(sys.argv[1:], 1):
    print(f"  Arg {i}: {arg}")
'''
        self.test_script_path.write_text(script_content)
        self.test_script_path.chmod(0o755)
        
    def create_test_app(self, dynamic: bool = True):
        """Create a test FastAPI app with dynamic terminal routes."""
        app_content = f'''#!/usr/bin/env python3
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
        "title": "Dynamic Test Terminal",
    }}
}}

# Configure the app with terminaide
terminaide.serve_apps(app, terminal_routes)

if __name__ == "__main__":
    # Start the server
    uvicorn.run(app, host="0.0.0.0", port={self.port})
'''
        self.test_app_path.write_text(app_content)
        self.test_app_path.chmod(0o755)
        
    def start_app(self, timeout: int = 10):
        """Start the test app and wait for it to be ready."""
        self.process = subprocess.Popen(
            ["python", str(self.test_app_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "TERMINAIDE_CURSOR_MGMT": "0"},  # Disable cursor management for tests
        )
        
        # Wait for HTTP server to start
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise RuntimeError(
                    f"Process exited early:\\nSTDOUT: {stdout}\\nSTDERR: {stderr}"
                )
                
            try:
                response = requests.get(f"http://localhost:{self.port}/test", timeout=1)
                if response.status_code == 200:
                    return
            except requests.exceptions.RequestException:
                pass
                
            time.sleep(0.5)
            
        raise TimeoutError(f"Server did not start within {timeout} seconds")
        
    def stop_app(self, timeout: int = 5):
        """Stop the test app gracefully."""
        if self.process is None:
            return
            
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            
    def cleanup(self):
        """Clean up test files and processes."""
        self.stop_app()
        
        # Remove test files
        if self.test_script_path.exists():
            self.test_script_path.unlink()
        if self.test_app_path.exists():
            self.test_app_path.unlink()
            
        # Clean up any temp parameter files
        temp_dir = Path("/tmp")
        for param_file in temp_dir.glob("terminaide_params_*.json"):
            try:
                param_file.unlink()
            except:
                pass
                
    def check_iframe_src(self, query_params: str = "") -> str:
        """Get the iframe src response text for further assertions by the caller."""
        url = f"http://localhost:{self.port}/test"
        if query_params:
            url += f"?{query_params}"
            
        response = requests.get(url, timeout=5)
        assert response.status_code == 200
        
        return response.text
        
    async def test_websocket_params(self, query_params: str = "") -> bool:
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
                param_file = Path("/tmp/terminaide_params__test.json")
                if param_file.exists():
                    data = json.loads(param_file.read_text())
                    return data
                    
                return None
        except Exception as e:
            print(f"WebSocket error: {e}")
            return None


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
        assert expected_src in response_text, f"Expected iframe src to contain '{expected_src}'"


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
        assert "args=--should-not-appear" not in response_text, "Non-dynamic routes should not pass query params"


def test_dynamic_wrapper_parsing():
    """Test the argument parsing logic directly."""
    from terminaide.core.wrappers import parse_args_query_param
    
    # Test basic parsing
    assert parse_args_query_param("--verbose") == ["--verbose"]
    assert parse_args_query_param("--mode,production") == ["--mode", "production"]
    assert parse_args_query_param("--flag1,value1,--flag2") == ["--flag1", "value1", "--flag2"]
    
    # Test edge cases
    assert parse_args_query_param("") == []
    assert parse_args_query_param("   ") == []
    assert parse_args_query_param("--trim  ,  spaces  ") == ["--trim", "spaces"]


def test_query_params_file_cleanup():
    """Test that parameter files are cleaned up properly."""
    from terminaide.core.wrappers import write_query_params_file, cleanup_stale_param_files
    
    # Create a test parameter file
    test_params = {"args": "--test"}
    param_file = write_query_params_file("/test", test_params)
    
    assert param_file.exists(), "Parameter file should exist"
    
    # Clean up stale files (with very short max age for testing)
    cleanup_stale_param_files(max_age_seconds=0)
    
    # File should be gone
    assert not param_file.exists(), "Parameter file should have been cleaned up"


def test_empty_query_params_file():
    """Test that empty parameter files are created and handled correctly."""
    from terminaide.core.wrappers import write_query_params_file
    
    # Create an empty parameter file (like proxy does when no query params)
    empty_params = {}
    param_file = write_query_params_file("/test-empty", empty_params)
    
    assert param_file.exists(), "Parameter file should exist even when empty"
    
    # Read back the content
    data = json.loads(param_file.read_text())
    assert data["type"] == "query_params"
    assert data["params"] == {}
    
    # Clean up
    param_file.unlink()


if __name__ == "__main__":
    # Run tests manually
    test_dynamic_route_basic()
    print("✓ Basic dynamic route test passed")
    
    test_dynamic_route_websocket_params()
    print("✓ WebSocket parameter test passed")
    
    test_non_dynamic_route()
    print("✓ Non-dynamic route test passed")
    
    test_dynamic_wrapper_parsing()
    print("✓ Argument parsing test passed")
    
    test_query_params_file_cleanup()
    print("✓ File cleanup test passed")
    
    test_empty_query_params_file()
    print("✓ Empty parameter file test passed")
    
    print("\nAll dynamic args tests passed!")