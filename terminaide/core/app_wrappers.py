# app_wrappers.py

"""
Script generation utilities for Terminaide.

This module contains functions that generate ephemeral Python scripts for wrapping
functions and scripts. These wrappers ensure proper path resolution,
module importing, and execution context.
"""

import os
import inspect
import logging
import tempfile
from pathlib import Path
from typing import Callable, Optional, Union, List

logger = logging.getLogger("terminaide")

# Global registry to track ephemeral files created by this process
_ephemeral_files_registry = set()


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


def extract_module_imports(func: Callable) -> str:
    """Extract import statements from the module containing the function."""
    imports = []
    
    try:
        # Get the module that contains the function
        module = inspect.getmodule(func)
        if module is None:
            return ""
        
        # Get the source file
        source_file = inspect.getsourcefile(func)
        if source_file is None:
            return ""
        
        # Read the source file and extract import statements
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        in_multiline_import = False
        for line in lines:
            stripped = line.strip()
            
            # Handle multiline imports
            if in_multiline_import:
                imports.append(line.rstrip())
                if ')' in line:
                    in_multiline_import = False
                continue
            
            # Single line imports
            if (stripped.startswith('import ') or 
                stripped.startswith('from ') or
                stripped.startswith('import\t') or 
                stripped.startswith('from\t')):
                imports.append(line.rstrip())
                
                # Check for multiline import starting
                if '(' in line and ')' not in line:
                    in_multiline_import = True
        
        return '\n'.join(imports) + '\n' if imports else ""
        
    except Exception:
        # If we can't extract imports, include common ones
        return "import sys\nimport os\n"


def generate_function_wrapper(func: Callable, args: Optional[List[str]] = None) -> Path:
    """
    Generate an ephemeral script for the given function. If it's in a real module,
    we do the normal import approach. If it's in __main__ or __mp_main__, inline fallback.
    """
    func_name = func.__name__
    module_name = getattr(func, "__module__", None)

    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    
    # Startup cleanup (safety net)
    cleanup_stale_ephemeral_files(temp_dir)
    
    script_path = temp_dir / f"{func_name}.py"

    # Determine the original source directory of the function
    try:
        source_file = inspect.getsourcefile(func) or inspect.getfile(func)
        source_dir = os.path.dirname(os.path.abspath(source_file))
    except Exception:
        source_dir = os.getcwd()  # fallback to current dir if all else fails

    # Check if function requires curses (has stdscr parameter)
    requires_curses = False
    try:
        sig = inspect.signature(func)
        if 'stdscr' in sig.parameters:
            requires_curses = True
    except Exception:
        pass

    # Generate bootstrap code
    bootstrap = generate_bootstrap_code(source_dir)
    
    # Generate sys.argv setup if args are provided
    argv_setup = ""
    if args:
        # Convert args to a properly quoted Python list
        args_repr = repr(args)
        argv_setup = f"import sys; sys.argv = ['{func_name}'] + {args_repr}\n"

    # If it's a normal module (not main or mp_main), we need to check if importing it 
    # would cause side effects (like serve_apps being called again)
    if module_name and module_name not in ("__main__", "__mp_main__", "main"):
        # Try import approach first for normal modules to avoid missing dependencies
        if requires_curses:
            call_line = f"    import curses; curses.wrapper({func_name})"
        else:
            call_line = f"    {func_name}()"
            
        wrapper_code = (
            f"# Ephemeral script for function {func_name} from module {module_name}\n"
            f"{bootstrap}"
            f"{argv_setup}"
            f"from {module_name} import {func_name}\n"
            f'if __name__ == "__main__":\n'
            f"{call_line}"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        
        # Track this file for cleanup on shutdown
        _ephemeral_files_registry.add(script_path)
        
        return script_path

    # Inline fallback (if __main__ or dynamically defined)
    try:
        source_code = inspect.getsource(func)
        module_imports = extract_module_imports(func)
        
        if requires_curses:
            call_line = f"    import curses; curses.wrapper({func_name})"
        else:
            call_line = f"    {func_name}()"
            
        wrapper_code = (
            f"# Inline wrapper for {func_name} (from __main__ or dynamic)\n"
            f"{bootstrap}"
            f"{module_imports}"
            f"{argv_setup}"
            f"{source_code}\n"
            f'if __name__ == "__main__":\n'
            f"{call_line}"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        
        # Track this file for cleanup on shutdown
        _ephemeral_files_registry.add(script_path)
        
        return script_path
    except Exception:
        # Last resort: static error fallback
        script_path.write_text(
            f'print("ERROR: cannot reload function {func_name} from module={module_name}")\n',
            encoding="utf-8",
        )
        
        # Track this file for cleanup on shutdown
        _ephemeral_files_registry.add(script_path)
        
        return script_path


def cleanup_stale_ephemeral_files(temp_dir: Path) -> None:
    """Clean up all ephemeral files on startup (safety net)."""
    try:
        cleaned_count = 0
        for file_path in temp_dir.glob("*.py"):
            try:
                file_path.unlink()
                cleaned_count += 1
            except (OSError, FileNotFoundError, PermissionError):
                continue
        
        if cleaned_count > 0:
            logger.debug(f"Startup cleanup: removed {cleaned_count} stale ephemeral files")
            
    except Exception as e:
        logger.debug(f"Startup cleanup failed (non-critical): {e}")


def cleanup_own_ephemeral_files() -> None:
    """Clean up ephemeral files created by this process (graceful shutdown)."""
    try:
        cleaned_count = 0
        for file_path in list(_ephemeral_files_registry):
            try:
                if file_path.exists():
                    file_path.unlink()
                    cleaned_count += 1
                _ephemeral_files_registry.discard(file_path)
            except (OSError, FileNotFoundError, PermissionError):
                continue
        
        if cleaned_count > 0:
            logger.debug(f"Graceful cleanup: removed {cleaned_count} ephemeral files")
            
    except Exception as e:
        logger.debug(f"Graceful cleanup failed (non-critical): {e}")


