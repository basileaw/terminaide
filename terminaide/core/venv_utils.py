# venv_utils.py

"""Virtual environment detection utilities for terminaide."""

import os
from pathlib import Path
from typing import Optional


def find_venv_python(script_path: str) -> Optional[str]:
    """
    Find the Python executable for a virtual environment associated with the given script.
    
    Searches from the script directory upward for common virtual environment patterns:
    - .venv/bin/python (Poetry, manual venv)
    - venv/bin/python (standard venv)
    - env/bin/python (common convention)
    
    Also checks for Poetry projects (pyproject.toml + .venv).
    
    Args:
        script_path: Path to the Python script
        
    Returns:
        Path to virtual environment Python executable, or None if not found
    """
    script_path = Path(script_path).resolve()
    
    # Start from script directory and search upward
    search_dir = script_path.parent
    
    # Common venv directory names to check
    venv_names = ['.venv', 'venv', 'env']
    
    # Search up the directory tree
    for current_dir in [search_dir] + list(search_dir.parents):
        # Check for common venv directories
        for venv_name in venv_names:
            venv_path = current_dir / venv_name
            python_path = venv_path / 'bin' / 'python'
            
            if python_path.exists() and python_path.is_file():
                # Verify it's executable
                if os.access(python_path, os.X_OK):
                    return str(python_path)
        
        # Check for Poetry project (pyproject.toml + .venv)
        pyproject_path = current_dir / 'pyproject.toml'
        if pyproject_path.exists():
            poetry_venv = current_dir / '.venv' / 'bin' / 'python'
            if poetry_venv.exists() and os.access(poetry_venv, os.X_OK):
                return str(poetry_venv)
        
        # Stop at filesystem root or when we find a git repo root
        if current_dir == current_dir.parent:
            break
        
        # Stop if we find a .git directory (project root)
        if (current_dir / '.git').exists():
            break
    
    return None


def has_venv_marker(directory: Path) -> bool:
    """
    Check if a directory contains virtual environment markers.
    
    Args:
        directory: Directory to check
        
    Returns:
        True if directory appears to contain a virtual environment
    """
    venv_markers = [
        'pyvenv.cfg',  # Standard venv marker
        'bin/python',  # Unix venv structure
        'lib/python',  # Python lib directory
    ]
    
    for marker in venv_markers:
        if (directory / marker).exists():
            return True
    
    return False