# app_wrappers.py

"""
Script generation utilities for Terminaide.

This module contains functions that generate ephemeral Python scripts for wrapping
functions, scripts, and meta-servers. These wrappers ensure proper path resolution,
module importing, and execution context.
"""

import os
import inspect
import logging
import tempfile
from pathlib import Path
from typing import Callable, Optional, Union

logger = logging.getLogger("terminaide")


def generate_bootstrap_code(source_dir: Union[str, Path], app_dir: Optional[Union[str, Path]] = None) -> str:
    """Generate bootstrap code for wrapper scripts.
    
    Args:
        source_dir: The source directory to add to sys.path
        app_dir: Optional application directory to add to sys.path
    
    Returns:
        Bootstrap code as a string
    """
    bootstrap_lines = [
        "import sys, os",
    ]
    
    if app_dir:
        bootstrap_lines.extend([
            "from pathlib import Path",
            f'app_dir = r"{app_dir}"',
            "if app_dir not in sys.path:",
            "    sys.path.insert(0, app_dir)",
        ])
    
    bootstrap_lines.extend([
        f'sys.path.insert(0, r"{source_dir}")',
        "sys.path.insert(0, os.getcwd())",
    ])
    
    return "\n".join(bootstrap_lines) + "\n\n"


def inline_source_code_wrapper(func: Callable) -> Optional[str]:
    """
    Attempt to inline the source code of 'func' if it's in __main__ or __mp_main__.
    Return the wrapper code as a string, or None if we can't get source code.
    """
    try:
        source_code = inspect.getsource(func)
    except OSError:
        return None

    func_name = func.__name__
    return f"""# Ephemeral inline function from main or mp_main
{source_code}
if __name__ == "__main__":
    {func_name}()"""


def generate_function_wrapper(func: Callable) -> Path:
    """
    Generate an ephemeral script for the given function. If it's in a real module,
    we do the normal import approach. If it's in __main__ or __mp_main__, inline fallback.
    """
    func_name = func.__name__
    module_name = getattr(func, "__module__", None)

    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    script_path = temp_dir / f"{func_name}.py"

    # Determine the original source directory of the function
    try:
        source_file = inspect.getsourcefile(func) or inspect.getfile(func)
        source_dir = os.path.dirname(os.path.abspath(source_file))
    except Exception:
        source_dir = os.getcwd()  # fallback to current dir if all else fails

    # Generate bootstrap code
    bootstrap = generate_bootstrap_code(source_dir)

    # If it's a normal module (not main or mp_main), we need to check if importing it 
    # would cause side effects (like serve_apps being called again)
    if module_name and module_name not in ("__main__", "__mp_main__"):
        # For now, try to get the source and inline it to avoid import side effects
        try:
            source_code = inspect.getsource(func)
            wrapper_code = (
                f"# Ephemeral script for function {func_name} from module {module_name}\n"
                f"# Using inline approach to avoid re-importing module with side effects\n"
                f"{bootstrap}"
                f"{source_code}\n"
                f'if __name__ == "__main__":\n'
                f"    {func_name}()"
            )
            script_path.write_text(wrapper_code, encoding="utf-8")
            return script_path
        except Exception:
            # If we can't get source, fall back to import (but this may cause issues)
            wrapper_code = (
                f"# Ephemeral script for function {func_name} from module {module_name}\n"
                f"{bootstrap}"
                f"from {module_name} import {func_name}\n"
                f'if __name__ == "__main__":\n'
                f"    {func_name}()"
            )
            script_path.write_text(wrapper_code, encoding="utf-8")
            return script_path

    # Inline fallback (if __main__ or dynamically defined)
    try:
        source_code = inspect.getsource(func)
        wrapper_code = (
            f"# Inline wrapper for {func_name} (from __main__ or dynamic)\n"
            f"{bootstrap}"
            f"{source_code}\n"
            f'if __name__ == "__main__":\n'
            f"    {func_name}()"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path
    except Exception:
        # Last resort: static error fallback
        script_path.write_text(
            f'print("ERROR: cannot reload function {func_name} from module={module_name}")\n',
            encoding="utf-8",
        )
        return script_path


def generate_meta_script_wrapper(
    script_path: Path, app_dir: Optional[Path] = None
) -> Path:
    """
    Generate an ephemeral script that runs a server script with correct path resolution
    without changing the working directory. This preserves the original working directory
    for file operations while ensuring imports and script resolution work correctly.

    Args:
        script_path: The server script to wrap
        app_dir: The application directory (if None, will use the script's directory)

    Returns:
        Path to the generated wrapper script
    """
    script_name = script_path.stem

    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    wrapper_script_path = temp_dir / f"meta_script_{script_name}.py"

    # Determine app directory if not provided
    if app_dir is None:
        app_dir = script_path.parent
        logger.debug(f"Using script directory as app_dir: {app_dir}")

    # Handle if app_dir is provided as a string
    if isinstance(app_dir, str):
        app_dir = Path(app_dir)

    # Generate the meta-specific bootstrap
    bootstrap = (
        "import sys, os\n"
        "from pathlib import Path\n"
        "import subprocess\n"
        "# Preserve original working directory for file operations\n"
        "original_cwd = os.getcwd()\n"
        f'app_dir = r"{app_dir}"\n'
        f'script_path = r"{script_path}"\n'
        "# Add paths to ensure imports work correctly\n"
        "if app_dir not in sys.path:\n"
        "    sys.path.insert(0, app_dir)\n"
        "if original_cwd not in sys.path:\n"
        "    sys.path.insert(0, original_cwd)\n"
        "# Monkey-patch sys.argv[0] to point to a file in the app directory\n"
        "# This ensures ScriptConfig validation resolves paths correctly\n"
        f'sys.argv[0] = str(Path(app_dir) / "main.py")\n\n'
        "# Override desktop mode to prevent infinite loops\n"
        "# Patch terminaide functions to force desktop=False in subprocess\n"
        "import terminaide.termin_api as termin_api\n"
        "original_meta_serve = termin_api.meta_serve\n"
        "def patched_meta_serve(*args, **kwargs):\n"
        "    kwargs['desktop'] = False  # Force web mode in subprocess\n"
        "    return original_meta_serve(*args, **kwargs)\n"
        "termin_api.meta_serve = patched_meta_serve\n\n"
        "# Execute the script using subprocess to maintain proper context\n"
        "try:\n"
        f"    result = subprocess.run([sys.executable, script_path], check=True)\n"
        "except subprocess.CalledProcessError as e:\n"
        f'    print(f"Error running script {script_path}: {{e}}")\n'
        "    sys.exit(e.returncode)\n"
        "except KeyboardInterrupt:\n"
        '    print("Script interrupted")\n'
        "    sys.exit(1)\n"
    )

    # Log the path setup on the meta-server side
    original_cwd = os.getcwd()
    logger.info(f"Meta-server starting from: {original_cwd}")
    logger.info(f"App directory added to path: {app_dir}")
    logger.info(f"Target script: {script_path}")

    wrapper_code = f"# Meta-server wrapper for script {script_name}\n" f"{bootstrap}"

    wrapper_script_path.write_text(wrapper_code, encoding="utf-8")
    return wrapper_script_path


def generate_meta_server_wrapper(
    func: Callable, app_dir: Optional[Path] = None
) -> Path:
    """
    Generate an ephemeral script that runs a server function with correct path resolution
    without changing the working directory. This preserves the original working directory
    for file operations while ensuring imports and script resolution work correctly.

    Args:
        func: The server function to wrap
        app_dir: The application directory (if None, will try to detect from function source)

    Returns:
        Path to the generated wrapper script
    """
    func_name = func.__name__
    module_name = getattr(func, "__module__", None)

    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    script_path = temp_dir / f"meta_server_{func_name}.py"

    # Determine source directory if not provided
    if app_dir is None:
        try:
            source_file = inspect.getsourcefile(func) or inspect.getfile(func)
            if source_file:
                app_dir = Path(os.path.dirname(os.path.abspath(source_file)))
                logger.debug(f"Detected app_dir from function source: {app_dir}")
        except Exception as e:
            logger.warning(f"Could not determine app_dir from function: {e}")
            app_dir = Path(os.getcwd())  # fallback to current dir if all else fails

    # Handle if app_dir is provided as a string
    if isinstance(app_dir, str):
        app_dir = Path(app_dir)

    # Generate the meta-specific bootstrap
    bootstrap = (
        "import sys, os\n"
        "from pathlib import Path\n"
        "# Preserve original working directory for file operations\n"
        "original_cwd = os.getcwd()\n"
        f'app_dir = r"{app_dir}"\n'
        "# Add paths to ensure imports work correctly\n"
        "if app_dir not in sys.path:\n"
        "    sys.path.insert(0, app_dir)\n"
        "if original_cwd not in sys.path:\n"
        "    sys.path.insert(0, original_cwd)\n"
        "# Monkey-patch sys.argv[0] to point to a file in the app directory\n"
        "# This ensures ScriptConfig validation resolves paths correctly\n"
        f'sys.argv[0] = str(Path(app_dir) / "main.py")\n\n'
    )

    # Log the path setup on the meta-server side
    original_cwd = os.getcwd()
    logger.info(f"Meta-server starting from: {original_cwd}")
    logger.info(f"App directory added to path: {app_dir}")

    # If it's a normal module (not main or mp_main)
    if module_name and module_name not in ("__main__", "__mp_main__"):
        wrapper_code = (
            f"# Meta-server wrapper for {func_name} from module {module_name}\n"
            f"{bootstrap}"
            f"# Import and run the server function (preserving working directory)\n"
            f"from {module_name} import {func_name}\n"
            f"{func_name}()\n"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path

    # Inline fallback (if __main__ or dynamically defined)
    try:
        source_code = inspect.getsource(func)

        wrapper_code = (
            f"# Meta-server wrapper for {func_name} (from __main__ or dynamic)\n"
            f"{bootstrap}"
            f"# Define the server function\n"
            f"{source_code}\n\n"
            f"# Run the server function (preserving working directory)\n"
            f"{func_name}()\n"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path
    except Exception as e:
        # Last resort: static error fallback
        error_script = (
            f'print("ERROR: cannot create meta-server wrapper for function {func_name}")\n'
            f'print("Module: {module_name}")\n'
            f'print("Error: {str(e)}")\n'
        )
        script_path.write_text(error_script, encoding="utf-8")
        return script_path