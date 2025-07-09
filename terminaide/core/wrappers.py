# wrappers.py

"""
Wrapper script generation utilities for Terminaide.

Provides function wrappers (ephemeral Python scripts) and dynamic wrappers
(scripts accepting runtime arguments via temp files).
"""

import os
import json
import time
import inspect
import logging
import tempfile
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Callable, Optional, List

logger = logging.getLogger("terminaide")
_ephemeral_files_registry = set()
_ephemeral_dir_cache = None
_function_signature_cache = {}


# Common Utilities
def get_ephemeral_dir() -> Path:
    """Get the standard ephemeral directory path (cached)."""
    global _ephemeral_dir_cache
    if _ephemeral_dir_cache is None:
        _ephemeral_dir_cache = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
        _ephemeral_dir_cache.mkdir(exist_ok=True, parents=True)
    return _ephemeral_dir_cache


@lru_cache(maxsize=256)
def sanitize_route_path(route_path: str) -> str:
    """Sanitize route path for use in filenames (cached)."""
    sanitized = route_path.replace("/", "_")
    return "_root" if sanitized == "_" else sanitized


def write_wrapper_file(file_path: Path, content: str, executable: bool = False) -> Path:
    """Write wrapper file and track it for cleanup (optimized I/O)."""
    # Write content in one operation
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Set permissions if needed
    if executable:
        file_path.chmod(0o755)

    # Track for cleanup
    _ephemeral_files_registry.add(file_path)
    return file_path


def detect_curses_requirement(func: Callable) -> bool:
    """Check if function requires curses (has stdscr parameter) - cached."""
    func_id = id(func)
    if func_id not in _function_signature_cache:
        try:
            _function_signature_cache[func_id] = (
                "stdscr" in inspect.signature(func).parameters
            )
        except Exception:
            _function_signature_cache[func_id] = False
    return _function_signature_cache[func_id]


@lru_cache(maxsize=256)
def generate_function_call_line(func_name: str, requires_curses: bool) -> str:
    """Generate the appropriate function call line (cached)."""
    return (
        f"    import curses; curses.wrapper({func_name})"
        if requires_curses
        else f"    {func_name}()"
    )


def safe_cleanup_file(file_path: Path, description: str = "file") -> bool:
    """Safely remove a file with error handling (optimized)."""
    try:
        file_path.unlink(missing_ok=True)  # Python 3.8+ optimized version
        return True
    except (OSError, PermissionError) as e:
        logger.debug(f"Error removing {description} {file_path}: {e}")
        return False


# Function Wrapper Utilities


@lru_cache(maxsize=128)
def generate_bootstrap_code(source_dir: str, app_dir: Optional[str] = None) -> str:
    """Generate bootstrap code for wrapper scripts (cached)."""
    # Pre-allocate list with known size for better performance
    lines = ["import sys, os"]
    if app_dir:
        lines.extend(
            [
                "from pathlib import Path",
                f'app_dir = r"{app_dir}"',
                "if app_dir not in sys.path:",
                "    sys.path.insert(0, app_dir)",
            ]
        )
    lines.extend(
        [f'sys.path.insert(0, r"{source_dir}")', "sys.path.insert(0, os.getcwd())"]
    )
    return "\n".join(lines) + "\n\n"


def inline_source_code_wrapper(func: Callable) -> Optional[str]:
    """Inline source code of func if possible."""
    try:
        source_code = inspect.getsource(func)
        func_name = func.__name__
        return f"# Ephemeral inline function\n{source_code}\nif __name__ == '__main__':\n    {func_name}()"
    except OSError:
        return None


@lru_cache(maxsize=64)
def extract_module_imports(source_file: str) -> str:
    """Extract import statements from the module containing the function (cached)."""
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        imports, in_multiline = [], False
        import_prefixes = ("import ", "from ", "import\t", "from\t")

        for line in lines:
            stripped = line.strip()
            if in_multiline:
                # Normalize indentation for multiline imports
                imports.append(stripped)
                if ")" in line:
                    in_multiline = False
            elif stripped.startswith(import_prefixes):
                # Only extract top-level imports (not indented ones inside functions)
                if not line.startswith(' ') and not line.startswith('\t'):
                    imports.append(stripped)
                    if "(" in line and ")" not in line:
                        in_multiline = True

        return "\n".join(imports) + "\n" if imports else ""
    except Exception:
        return "import sys\nimport os\n"


def get_module_imports_for_func(func: Callable) -> str:
    """Get module imports for a function (wrapper for caching)."""
    try:
        module = inspect.getmodule(func)
        source_file = inspect.getsourcefile(func)
        if not module or not source_file:
            return ""
        return extract_module_imports(source_file)
    except Exception:
        return "import sys\nimport os\n"


def generate_function_wrapper(func: Callable, args: Optional[List[str]] = None) -> Path:
    """Generate an ephemeral script for the given function (optimized)."""
    func_name, module_name = func.__name__, getattr(func, "__module__", None)
    temp_dir = get_ephemeral_dir()
    script_path = temp_dir / f"{func_name}.py"

    # Get source directory (optimized path operations)
    try:
        source_file = inspect.getsourcefile(func) or inspect.getfile(func)
        source_dir = str(Path(source_file).parent.resolve())
    except Exception as e:
        source_dir = os.getcwd()
        logger.debug(f"Could not get source directory, using cwd: {source_dir}, error: {e}")

    requires_curses = detect_curses_requirement(func)
    bootstrap = generate_bootstrap_code(source_dir)
    argv_setup = (
        f"import sys; sys.argv = ['{func_name}'] + {repr(args)}\n" if args else ""
    )
    call_line = generate_function_call_line(func_name, requires_curses)

    # Import approach for normal modules
    if module_name and module_name not in ("__main__", "__mp_main__", "main"):
        # Use string concatenation for better performance than f-strings in loops
        wrapper_code = (
            "# Ephemeral script for "
            + func_name
            + "\n"
            + bootstrap
            + argv_setup
            + "from "
            + module_name
            + " import "
            + func_name
            + "\nif __name__ == '__main__':\n"
            + call_line
        )
        return write_wrapper_file(script_path, wrapper_code)

    # Inline fallback
    try:
        source_code = inspect.getsource(func)
        module_imports = get_module_imports_for_func(func)
        wrapper_code = (
            "# Inline wrapper for "
            + func_name
            + "\n"
            + bootstrap
            + module_imports
            + argv_setup
            + source_code
            + "\nif __name__ == '__main__':\n"
            + call_line
        )
        return write_wrapper_file(script_path, wrapper_code)
    except Exception as e:
        logger.warning(f"Failed to inline function source, creating error wrapper: {e}")
        error_content = (
            'print("ERROR: cannot reload function '
            + func_name
            + " from module="
            + str(module_name)
            + '")\n'
        )
        return write_wrapper_file(script_path, error_content)


def cleanup_stale_ephemeral_files(temp_dir: Path) -> None:
    """Clean up all ephemeral files on startup (safety net, optimized)."""
    try:
        # Use glob pattern matching for better performance
        py_files = list(temp_dir.glob("*.py"))
        if not py_files:
            return

        cleaned_count = sum(
            1
            for file_path in py_files
            if safe_cleanup_file(file_path, "ephemeral file")
        )
        if cleaned_count > 0:
            logger.debug(
                f"Startup cleanup: removed {cleaned_count} stale ephemeral files"
            )
    except Exception as e:
        logger.debug(f"Startup cleanup failed (non-critical): {e}")


def cleanup_own_ephemeral_files() -> None:
    """Clean up ephemeral files created by this process (graceful shutdown)."""
    try:
        cleaned_count = 0
        for file_path in list(_ephemeral_files_registry):
            if safe_cleanup_file(file_path, "registered ephemeral file"):
                cleaned_count += 1
            _ephemeral_files_registry.discard(file_path)
        if cleaned_count > 0:
            logger.debug(f"Graceful cleanup: removed {cleaned_count} ephemeral files")
    except Exception as e:
        logger.debug(f"Graceful cleanup failed (non-critical): {e}")


# Dynamic Wrapper Utilities


def generate_dynamic_wrapper_script(
    script_path: Path,
    static_args: List[str],
    python_executable: str = "python",
    args_param: str = "args",
) -> str:
    """
    Generate a Python wrapper script that waits for dynamic arguments from a temp file.

    Args:
        script_path: Path to the actual script to run
        static_args: List of static arguments always passed to the script
        python_executable: Python executable to use
        args_param: Name of the query parameter containing arguments

    Returns:
        The wrapper script content as a string
    """
    # Escape arguments for safe inclusion in the script
    static_args_repr = repr(static_args)
    script_path_str = str(script_path)

    wrapper_content = dedent(
        f"""
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
                args_str = params.get("{args_param}", "")
                
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
"""
    ).strip()

    return wrapper_content


def create_dynamic_wrapper_file(
    script_path: Path,
    static_args: List[str],
    route_path: str,
    wrapper_dir: Optional[Path] = None,
    python_executable: str = "python",
    args_param: str = "args",
) -> Path:
    """
    Create a dynamic wrapper script file for a given script.

    Args:
        script_path: Path to the actual script to run
        static_args: List of static arguments always passed to the script
        route_path: The route path this wrapper is for (used in filename)
        wrapper_dir: Directory to create wrapper in (defaults to temp dir)
        python_executable: Python executable to use
        args_param: Name of the query parameter containing arguments

    Returns:
        Path to the created wrapper script
    """
    # Generate wrapper content
    wrapper_content = generate_dynamic_wrapper_script(
        script_path, static_args, python_executable, args_param
    )

    # Determine wrapper directory
    if wrapper_dir is None:
        wrapper_dir = get_ephemeral_dir()
    else:
        wrapper_dir.mkdir(exist_ok=True, parents=True)

    # Create wrapper filename based on route path
    sanitized_route = sanitize_route_path(route_path)

    wrapper_filename = f"dynamic_wrapper{sanitized_route}_{os.getpid()}.py"
    wrapper_path = wrapper_dir / wrapper_filename

    # Write wrapper script
    write_wrapper_file(wrapper_path, wrapper_content, executable=True)

    logger.debug(f"Created dynamic wrapper at {wrapper_path} for route {route_path}")

    return wrapper_path


def parse_args_query_param(args_str: str, args_param: str = "args") -> List[str]:
    """
    Parse the query parameter into a list of arguments.

    Args:
        args_str: Comma-separated string of arguments, e.g., "--verbose,--mode,production"
        args_param: Name of the query parameter (for documentation purposes)

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
    sanitized_route = sanitize_route_path(route_path)

    # Create temp file path
    param_file = Path(f"/tmp/terminaide_params_{sanitized_route}.json")

    # Write parameters
    data = {"type": "query_params", "params": query_params, "timestamp": time.time()}

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
                    if safe_cleanup_file(param_file, "stale param file"):
                        logger.debug(f"Cleaned up stale param file: {param_file}")
            except Exception as e:
                logger.debug(f"Error checking age of {param_file}: {e}")
    except Exception as e:
        logger.debug(f"Error during param file cleanup: {e}")
