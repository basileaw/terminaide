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
import shutil
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Callable, Optional, List, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import TerminaideConfig

logger = logging.getLogger("terminaide")
_ephemeral_files_registry = set()
_ephemeral_dir_cache = None
_function_signature_cache = {}


# Common Utilities
def _test_directory_writable(directory: Path) -> None:
    """Test if directory is writable by creating and removing a test file."""
    test_file = directory / f".write_test_{os.getpid()}"
    test_file.touch()
    test_file.unlink()


def _get_package_cache_dir() -> Path:
    """Get package-based cache directory for scripts."""
    package_root = Path(__file__).parent.parent  # terminaide/
    return package_root / "cache" / "scripts"


def _get_package_params_cache_dir() -> Path:
    """Get package-based cache directory for parameter files."""
    package_root = Path(__file__).parent.parent  # terminaide/
    return package_root / "cache" / "params"




def _resolve_cache_directory(config: Optional[Any] = None, cache_type: str = "scripts") -> Path:
    """Resolve cache directory in priority order.
    
    Args:
        config: Optional configuration object with cache directory override
        cache_type: Type of cache ("scripts" or "params")
    """
    
    # 1. Explicit config parameter (highest priority)
    if config and hasattr(config, 'ephemeral_cache_dir') and config.ephemeral_cache_dir:
        cache_dir = config.ephemeral_cache_dir / cache_type
        logger.debug(f"Using configured cache directory: {cache_dir}")
        try:
            cache_dir.mkdir(exist_ok=True, parents=True)
            _test_directory_writable(cache_dir)
            return cache_dir
        except (PermissionError, OSError) as e:
            raise RuntimeError(f"Configured cache directory not writable: {cache_dir}") from e
    
    # 2. Environment variable override
    if env_dir := os.environ.get("TERMINAIDE_CACHE_DIR"):
        cache_dir = Path(env_dir) / cache_type
        logger.debug(f"Using environment cache directory: {cache_dir}")
        try:
            cache_dir.mkdir(exist_ok=True, parents=True)
            _test_directory_writable(cache_dir)
            return cache_dir
        except (PermissionError, OSError) as e:
            raise RuntimeError(f"Environment cache directory not writable: {cache_dir}") from e
    
    # 3. Package cache (only fallback)
    try:
        if cache_type == "params":
            cache_dir = _get_package_params_cache_dir()
        else:
            cache_dir = _get_package_cache_dir()
        cache_dir.mkdir(exist_ok=True, parents=True)
        _test_directory_writable(cache_dir)
        logger.debug(f"Using package cache directory: {cache_dir}")
        return cache_dir
    except (PermissionError, OSError) as e:
        logger.debug(f"Package cache not available: {e}")
        raise RuntimeError(
            f"Package cache directory not writable and no explicit cache configured: {cache_dir}. "
            "To use external directories, set ephemeral_cache_dir in TerminaideConfig or "
            "set the TERMINAIDE_CACHE_DIR environment variable."
        ) from e


def get_ephemeral_dir(config: Optional[Any] = None, force_refresh: bool = False) -> Path:
    """Get the ephemeral directory path with configurable cache support.
    
    Args:
        config: Optional configuration object with cache directory override
        force_refresh: If True, bypass cache and resolve directory fresh
    
    Returns:
        Path to the scripts directory (for backward compatibility)
    """
    global _ephemeral_dir_cache
    
    # If config provided or force refresh, resolve fresh
    if config or force_refresh or _ephemeral_dir_cache is None:
        resolved_dir = _resolve_cache_directory(config, "scripts")
        
        # Only cache if no config override (to avoid config bleeding between calls)
        if not config:
            _ephemeral_dir_cache = resolved_dir
        
        return resolved_dir
    
    # Use cached directory for simple calls
    return _ephemeral_dir_cache


def get_params_dir(config: Optional[Any] = None) -> Path:
    """Get the parameter files directory path.
    
    Args:
        config: Optional configuration object with cache directory override
    
    Returns:
        Path to the params directory
    """
    return _resolve_cache_directory(config, "params")


@lru_cache(maxsize=256)
def sanitize_route_path(route_path: str) -> str:
    """Sanitize route path for use in filenames (cached)."""
    sanitized = route_path.replace("/", "_")
    return "_root" if sanitized == "_" else sanitized


def write_wrapper_file(file_path: Path, content: str, executable: bool = False, register_for_cleanup: bool = True) -> Path:
    """Write wrapper file and optionally track it for cleanup (optimized I/O)."""
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write content in one operation
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Set permissions if needed
    if executable:
        file_path.chmod(0o755)

    # Track for cleanup only if requested
    if register_for_cleanup:
        _ephemeral_files_registry.add(file_path)
        logger.debug(f"File added to cleanup registry: {file_path}")
    else:
        logger.debug(f"File NOT registered for cleanup: {file_path}")
    
    logger.debug(f"Successfully wrote wrapper file: {file_path}")
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
                if not line.startswith(" ") and not line.startswith("\t"):
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


def ensure_script_exists(script_path: Path, regenerate_func: Callable[[], Path]) -> Path:
    """Ensure script exists, regenerating if missing (lazy validation).
    
    Args:
        script_path: Expected path to the script
        regenerate_func: Function to call to regenerate the script
    
    Returns:
        Path to the verified script
    """
    if script_path.exists():
        return script_path
    
    logger.info(f"Ephemeral script missing, regenerating: {script_path}")
    return regenerate_func()


def get_or_ensure_function_wrapper(
    func: Callable, 
    args: Optional[List[str]] = None, 
    config: Optional[Any] = None
) -> Path:
    """Get function wrapper script, regenerating if missing (lazy validation + configurable cache).
    
    Args:
        func: The function to wrap
        args: Optional arguments to pass to the function
        config: Optional configuration with cache directory override
    
    Returns:
        Path to the verified wrapper script
    """
    func_name = func.__name__
    temp_dir = get_ephemeral_dir(config)
    expected_path = temp_dir / f"{func_name}.py"
    
    def regenerate():
        return generate_function_wrapper(func, args=args, config=config)
    
    return ensure_script_exists(expected_path, regenerate)


def generate_function_wrapper(
    func: Callable, 
    args: Optional[List[str]] = None, 
    config: Optional[Any] = None
) -> Path:
    """Generate an ephemeral script for the given function (optimized with configurable cache).
    
    Args:
        func: The function to wrap
        args: Optional arguments to pass to the function
        config: Optional configuration with cache directory override
    
    Returns:
        Path to the generated script
    """
    func_name, module_name = func.__name__, getattr(func, "__module__", None)
    temp_dir = get_ephemeral_dir(config)
    script_path = temp_dir / f"{func_name}.py"
    
    logger.debug(f"Generating wrapper for function {func_name} from module {module_name}")
    logger.debug(f"Target script path: {script_path}")

    # Get source directory (optimized path operations)
    try:
        source_file = inspect.getsourcefile(func) or inspect.getfile(func)
        source_dir = str(Path(source_file).parent.resolve())
        logger.debug(f"Source file: {source_file}, source dir: {source_dir}")
    except Exception as e:
        source_dir = os.getcwd()
        logger.debug(
            f"Could not get source directory, using cwd: {source_dir}, error: {e}"
        )

    requires_curses = detect_curses_requirement(func)
    bootstrap = generate_bootstrap_code(source_dir)
    argv_setup = (
        f"import sys; sys.argv = ['{func_name}'] + {repr(args)}\n" if args else ""
    )
    call_line = generate_function_call_line(func_name, requires_curses)

    # Import approach for normal modules
    if module_name and module_name not in ("__main__", "__mp_main__", "main"):
        logger.debug(f"Using import approach for module {module_name}")
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
        # Don't register function wrappers for cleanup - they need to persist for ttyd
        return write_wrapper_file(script_path, wrapper_code, register_for_cleanup=False)

    # Inline fallback
    logger.debug(f"Using inline approach for function {func_name}")
    try:
        source_code = inspect.getsource(func)
        logger.debug(f"Got source code for {func_name}: {len(source_code)} chars")
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
        logger.debug(f"Generated wrapper code: {len(wrapper_code)} chars")
        # Don't register function wrappers for cleanup - they need to persist for ttyd
        return write_wrapper_file(script_path, wrapper_code, register_for_cleanup=False)
    except Exception as e:
        logger.error(f"Failed to inline function source for {func_name}: {e}")
        logger.warning(f"Failed to inline function source, creating error wrapper: {e}")
        error_content = (
            'print("ERROR: cannot reload function '
            + func_name
            + " from module="
            + str(module_name)
            + '")\n'
        )
        # Error wrappers should be cleaned up
        return write_wrapper_file(script_path, error_content, register_for_cleanup=True)


def cleanup_stale_ephemeral_files(config: Optional[Any] = None) -> None:
    """Clean up all ephemeral files on startup (safety net, optimized).
    
    Args:
        config: Optional configuration to determine cache directory
    """
    # Run cache migration first, before cleaning up
    migrate_cache_structure()
    
    try:
        temp_dir = get_ephemeral_dir(config)  # This now points to scripts directory
        
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
                f"Startup cleanup: removed {cleaned_count} stale ephemeral files from {temp_dir}"
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
    cache_dir: Optional[Path] = None,
) -> str:
    """
    Generate a Python wrapper script that waits for dynamic arguments from a temp file.

    Args:
        script_path: Path to the actual script to run
        static_args: List of static arguments always passed to the script
        python_executable: Python executable to use
        args_param: Name of the query parameter containing arguments
        cache_dir: Cache directory for parameter files (if None, uses ephemeral cache)

    Returns:
        The wrapper script content as a string
    """
    # Escape arguments for safe inclusion in the script
    static_args_repr = repr(static_args)
    script_path_str = str(script_path)

    # Get cache directory for parameter files
    if cache_dir is None:
        cache_dir = get_params_dir()
    cache_dir_str = str(cache_dir)

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

# Construct parameter file path in cache directory
cache_dir = Path({repr(cache_dir_str)})
param_file = cache_dir / f"terminaide_params_{{sanitized_route}}.json"

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
cmd = [{repr(python_executable)}, script_path] + all_args

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
    config: Optional[Any] = None,
) -> Path:
    """
    Create a dynamic wrapper script file for a given script.

    Args:
        script_path: Path to the actual script to run
        static_args: List of static arguments always passed to the script
        route_path: The route path this wrapper is for (used in filename)
        wrapper_dir: Directory to create wrapper in (defaults to ephemeral cache dir)
        python_executable: Python executable to use
        args_param: Name of the query parameter containing arguments
        config: Optional configuration with cache directory override

    Returns:
        Path to the created wrapper script
    """
    # Determine cache directory for parameter files
    params_cache_dir = get_params_dir(config)
    
    # Generate wrapper content
    wrapper_content = generate_dynamic_wrapper_script(
        script_path, static_args, python_executable, args_param, params_cache_dir
    )

    # Determine wrapper directory
    if wrapper_dir is None:
        wrapper_dir = get_ephemeral_dir(config)
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


def write_query_params_file(route_path: str, query_params: dict, config: Optional[Any] = None) -> Path:
    """
    Write query parameters to a file for the dynamic wrapper to read.

    Args:
        route_path: The route path (used to generate filename)
        query_params: Dictionary of query parameters
        config: Optional configuration with cache directory override

    Returns:
        Path to the created parameter file
    """
    # Sanitize route path for filename
    sanitized_route = sanitize_route_path(route_path)

    # Create parameter file path in params cache directory
    cache_dir = get_params_dir(config)
    param_file = cache_dir / f"terminaide_params_{sanitized_route}.json"

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


def cleanup_stale_param_files(max_age_seconds: int = 300, config: Optional[Any] = None) -> None:
    """
    Clean up old parameter files that may have been left behind.

    Args:
        max_age_seconds: Remove files older than this many seconds
        config: Optional configuration with cache directory override
    """
    try:
        current_time = time.time()
        cache_dir = get_params_dir(config)

        for param_file in cache_dir.glob("terminaide_params_*.json"):
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


def migrate_cache_structure() -> None:
    """
    Migrate existing cache files to the new directory structure.
    
    This function is called on startup to move files from the old structure:
    - cache/ephemeral/ -> cache/scripts/ and cache/params/  
    - cache/monitor.log -> cache/logs/monitor.log
    - bin/ttyd -> cache/binaries/ttyd
    - custom preview images in static/ -> cache/assets/ (copies)
    """
    try:
        package_root = Path(__file__).parent.parent  # terminaide/
        
        # 1. Migrate ephemeral files to scripts and params directories
        old_ephemeral_dir = package_root / "cache" / "ephemeral"
        if old_ephemeral_dir.exists():
            scripts_dir = package_root / "cache" / "scripts"
            params_dir = package_root / "cache" / "params"
            scripts_dir.mkdir(exist_ok=True, parents=True)
            params_dir.mkdir(exist_ok=True, parents=True)
            
            moved_count = 0
            for file_path in old_ephemeral_dir.iterdir():
                if file_path.is_file():
                    if file_path.name.startswith("terminaide_params_") and file_path.suffix == ".json":
                        # Move parameter files to params directory
                        new_path = params_dir / file_path.name
                        if not new_path.exists():
                            file_path.rename(new_path)
                            moved_count += 1
                            logger.debug(f"Migrated parameter file: {file_path} -> {new_path}")
                    elif file_path.suffix == ".py":
                        # Move Python scripts to scripts directory
                        new_path = scripts_dir / file_path.name
                        if not new_path.exists():
                            file_path.rename(new_path)
                            moved_count += 1
                            logger.debug(f"Migrated script file: {file_path} -> {new_path}")
            
            # Remove old ephemeral directory if empty
            try:
                if not any(old_ephemeral_dir.iterdir()):
                    old_ephemeral_dir.rmdir()
                    logger.debug(f"Removed empty ephemeral directory: {old_ephemeral_dir}")
            except OSError:
                pass  # Directory not empty or other issue
            
            if moved_count > 0:
                logger.info(f"Migrated {moved_count} files from ephemeral directory to new structure")
        
        # 2. Migrate monitor log
        old_monitor_log = package_root / "cache" / "monitor.log"
        if old_monitor_log.exists():
            logs_dir = package_root / "cache" / "logs"
            logs_dir.mkdir(exist_ok=True, parents=True)
            new_monitor_log = logs_dir / "monitor.log"
            if not new_monitor_log.exists():
                old_monitor_log.rename(new_monitor_log)
                logger.info(f"Migrated monitor log: {old_monitor_log} -> {new_monitor_log}")
        
        # 3. Migrate ttyd binary
        old_ttyd_binary = package_root / "bin" / "ttyd"
        if old_ttyd_binary.exists():
            binaries_dir = package_root / "cache" / "binaries"
            binaries_dir.mkdir(exist_ok=True, parents=True)
            new_ttyd_binary = binaries_dir / "ttyd"
            if not new_ttyd_binary.exists():
                old_ttyd_binary.rename(new_ttyd_binary)
                logger.info(f"Migrated ttyd binary: {old_ttyd_binary} -> {new_ttyd_binary}")
                
                # Remove old bin directory if empty
                try:
                    old_bin_dir = package_root / "bin"
                    if not any(old_bin_dir.iterdir()):
                        old_bin_dir.rmdir()
                        logger.debug(f"Removed empty bin directory: {old_bin_dir}")
                except OSError:
                    pass  # Directory not empty or other issue
        
        # 4. Copy custom preview images from static/ to cache/assets/
        static_dir = package_root / "static"
        if static_dir.exists():
            assets_dir = package_root / "cache" / "assets"
            assets_dir.mkdir(exist_ok=True, parents=True)
            
            copied_count = 0
            for file_path in static_dir.iterdir():
                if file_path.is_file() and file_path.name.startswith("preview_") and file_path.name != "preview.png":
                    # This is a custom preview image (not the default one)
                    assets_path = assets_dir / file_path.name
                    if not assets_path.exists():
                        shutil.copy2(file_path, assets_path)
                        copied_count += 1
                        logger.debug(f"Copied custom preview image to assets: {file_path} -> {assets_path}")
            
            if copied_count > 0:
                logger.info(f"Copied {copied_count} custom preview images to assets directory")
    
    except Exception as e:
        logger.warning(f"Cache migration encountered errors (non-critical): {e}")
