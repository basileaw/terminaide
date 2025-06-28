# dynamic_wrapper.py

"""Dynamic wrapper script generator for terminaide."""

import os
import json
import time
import tempfile
from pathlib import Path
from textwrap import dedent
from typing import List, Optional

import logging

logger = logging.getLogger("terminaide")


def generate_dynamic_wrapper_script(
    script_path: Path,
    static_args: List[str],
    python_executable: str = "python",
) -> str:
    """
    Generate a Python wrapper script that waits for dynamic arguments from a temp file.
    
    Args:
        script_path: Path to the actual script to run
        static_args: List of static arguments always passed to the script
        python_executable: Python executable to use
        
    Returns:
        The wrapper script content as a string
    """
    # Escape arguments for safe inclusion in the script
    static_args_repr = repr(static_args)
    script_path_str = str(script_path)
    
    wrapper_content = dedent(f'''
#!/usr/bin/env {python_executable}
# Dynamic wrapper script for terminaide

import os
import sys
import json
import time
import subprocess
from pathlib import Path

# Get route path from environment
route_path = os.environ.get("TERMINAIDE_ROUTE_PATH", "/")
sanitized_route = route_path.replace("/", "_")
if sanitized_route == "_":
    sanitized_route = "_root"

# Construct temp file path
param_file = f"/tmp/terminaide_params_{{sanitized_route}}.json"

# Static configuration
script_path = {repr(script_path_str)}
static_args = {static_args_repr}

# Wait for parameter file (with timeout)
max_wait_time = 2.0  # seconds (reduced since proxy always writes file now)
wait_interval = 0.1  # seconds
waited_time = 0.0

dynamic_args = []

while waited_time < max_wait_time:
    if os.path.exists(param_file):
        try:
            with open(param_file, "r") as f:
                data = json.load(f)
            
            # Extract query parameters
            if data.get("type") == "query_params":
                params = data.get("params", {{}})
                args_str = params.get("args", "")
                
                # Parse comma-separated args
                if args_str:
                    dynamic_args = [arg.strip() for arg in args_str.split(",") if arg.strip()]
            
            # Clean up temp file immediately after reading
            try:
                os.unlink(param_file)
            except:
                pass
            
            break
        except (json.JSONDecodeError, IOError) as e:
            # Invalid or incomplete file, wait and retry
            pass
    
    time.sleep(wait_interval)
    waited_time += wait_interval

# If no file found after timeout, proceed with static args only
if not dynamic_args and waited_time >= max_wait_time:
    print(f"[Dynamic wrapper] No parameters file found after {{max_wait_time}}s, using static args only", file=sys.stderr)

# Merge static and dynamic arguments
all_args = static_args + dynamic_args

# Launch the actual script
cmd = [sys.executable, script_path] + all_args

# Execute the script, forwarding all I/O
try:
    sys.exit(subprocess.call(cmd))
except Exception as e:
    print(f"[Dynamic wrapper] Error launching script: {{e}}", file=sys.stderr)
    sys.exit(1)
''').strip()
    
    return wrapper_content


def create_dynamic_wrapper_file(
    script_path: Path,
    static_args: List[str],
    route_path: str,
    wrapper_dir: Optional[Path] = None,
    python_executable: str = "python",
) -> Path:
    """
    Create a dynamic wrapper script file for a given script.
    
    Args:
        script_path: Path to the actual script to run
        static_args: List of static arguments always passed to the script
        route_path: The route path this wrapper is for (used in filename)
        wrapper_dir: Directory to create wrapper in (defaults to temp dir)
        python_executable: Python executable to use
        
    Returns:
        Path to the created wrapper script
    """
    # Generate wrapper content
    wrapper_content = generate_dynamic_wrapper_script(
        script_path, static_args, python_executable
    )
    
    # Determine wrapper directory
    if wrapper_dir is None:
        wrapper_dir = Path(tempfile.gettempdir()) / "terminaide_wrappers"
    wrapper_dir.mkdir(exist_ok=True, parents=True)
    
    # Create wrapper filename based on route path
    sanitized_route = route_path.replace("/", "_")
    if sanitized_route == "_":
        sanitized_route = "_root"
    
    wrapper_filename = f"dynamic_wrapper{sanitized_route}_{os.getpid()}.py"
    wrapper_path = wrapper_dir / wrapper_filename
    
    # Write wrapper script
    wrapper_path.write_text(wrapper_content)
    wrapper_path.chmod(0o755)  # Make executable
    
    logger.debug(f"Created dynamic wrapper at {wrapper_path} for route {route_path}")
    
    return wrapper_path


def parse_args_query_param(args_str: str) -> List[str]:
    """
    Parse the 'args' query parameter into a list of arguments.
    
    Args:
        args_str: Comma-separated string of arguments, e.g., "--verbose,--mode,production"
        
    Returns:
        List of parsed arguments, e.g., ["--verbose", "--mode", "production"]
    """
    if not args_str:
        return []
    
    return [arg.strip() for arg in args_str.split(",") if arg.strip()]


def write_query_params_file(route_path: str, query_params: dict) -> Path:
    """
    Write query parameters to a temp file for the dynamic wrapper to read.
    
    Args:
        route_path: The route path (used to generate filename)
        query_params: Dictionary of query parameters
        
    Returns:
        Path to the created temp file
    """
    # Sanitize route path for filename
    sanitized_route = route_path.replace("/", "_")
    if sanitized_route == "_":
        sanitized_route = "_root"
    
    # Create temp file path
    param_file = Path(f"/tmp/terminaide_params_{sanitized_route}.json")
    
    # Write parameters
    data = {
        "type": "query_params",
        "params": query_params,
        "timestamp": time.time()
    }
    
    try:
        with open(param_file, "w") as f:
            json.dump(data, f)
        
        # Set restrictive permissions
        param_file.chmod(0o600)
        
        logger.debug(f"Wrote query params to {param_file} for route {route_path}")
        return param_file
    except Exception as e:
        logger.error(f"Failed to write query params file: {e}")
        raise


def cleanup_stale_param_files(max_age_seconds: int = 300) -> None:
    """
    Clean up old parameter files that may have been left behind.
    
    Args:
        max_age_seconds: Remove files older than this many seconds
    """
    try:
        current_time = time.time()
        temp_dir = Path("/tmp")
        
        for param_file in temp_dir.glob("terminaide_params_*.json"):
            try:
                # Check file age
                file_age = current_time - param_file.stat().st_mtime
                if file_age > max_age_seconds:
                    param_file.unlink()
                    logger.debug(f"Cleaned up stale param file: {param_file}")
            except Exception as e:
                logger.debug(f"Error cleaning up {param_file}: {e}")
    except Exception as e:
        logger.debug(f"Error during param file cleanup: {e}")