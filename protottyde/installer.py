# protottyde/installer.py

"""
TTYd binary installation and setup.

This module handles downloading and setting up the ttyd binary for both
x86_64 Linux (Docker) and ARM64 (Apple Silicon) environments.
"""

import os
import sys
import stat
import shutil
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import urllib.request

logger = logging.getLogger("protottyde")

TTYD_VERSION = "1.7.3"
TTYD_GITHUB_BASE = f"https://github.com/tsl0922/ttyd/releases/download/{TTYD_VERSION}"

# Mapping of platform to binary URL and filename
PLATFORM_BINARIES = {
    ("Linux", "x86_64"): (f"{TTYD_GITHUB_BASE}/ttyd.x86_64", "ttyd"),
    ("Darwin", "arm64"): (f"{TTYD_GITHUB_BASE}/ttyd.arm64", "ttyd"),
}

def get_platform_info() -> Tuple[str, str]:
    """Get current platform and architecture."""
    system = platform.system()
    machine = platform.machine()
    
    # Normalize ARM architecture names
    if machine in ["arm64", "aarch64"]:
        machine = "arm64"
    
    return system, machine

def get_binary_dir() -> Path:
    """Get the directory where the ttyd binary should be installed."""
    # Use ~/.local/bin on Linux, ~/Library/Application Support on macOS
    if platform.system() == "Darwin":
        base_dir = Path.home() / "Library" / "Application Support" / "protottyde"
    else:
        base_dir = Path.home() / ".local" / "share" / "protottyde"
    
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir

def download_binary(url: str, target_path: Path) -> None:
    """Download the ttyd binary from GitHub."""
    logger.info(f"Downloading ttyd from {url}")
    try:
        urllib.request.urlretrieve(url, target_path)
        # Make binary executable
        target_path.chmod(target_path.stat().st_mode | stat.S_IEXEC)
    except Exception as e:
        raise RuntimeError(f"Failed to download ttyd: {e}")

def verify_dependencies() -> None:
    """Verify that required system libraries are available."""
    required_libs = ["libwebsockets.so", "libjson-c.so"]
    
    if platform.system() == "Linux":
        try:
            output = subprocess.check_output(["ldconfig", "-p"]).decode()
            missing = [lib for lib in required_libs if lib not in output]
            if missing:
                raise RuntimeError(
                    f"Missing required libraries: {', '.join(missing)}. "
                    "Please install libwebsockets-dev and libjson-c-dev."
                )
        except subprocess.CalledProcessError:
            logger.warning("Could not verify dependencies with ldconfig")

def get_ttyd_path() -> Optional[Path]:
    """Get path to installed ttyd binary, installing if necessary."""
    system, machine = get_platform_info()
    platform_key = (system, machine)
    
    if platform_key not in PLATFORM_BINARIES:
        raise RuntimeError(
            f"Unsupported platform: {system} {machine}. "
            "Only Linux x86_64 and macOS ARM64 are supported."
        )
    
    url, binary_name = PLATFORM_BINARIES[platform_key]
    binary_dir = get_binary_dir()
    binary_path = binary_dir / binary_name
    
    # Check if binary exists and is executable
    if not binary_path.exists() or not os.access(binary_path, os.X_OK):
        verify_dependencies()
        download_binary(url, binary_path)
    
    return binary_path

def setup_ttyd() -> Path:
    """
    Ensure ttyd is installed and return its path.
    
    This is the main entry point for the installer module.
    """
    try:
        # First check if ttyd is in PATH
        ttyd_in_path = shutil.which("ttyd")
        if ttyd_in_path:
            return Path(ttyd_in_path)
        
        # If not in PATH, install/get our managed version
        binary_path = get_ttyd_path()
        if binary_path and os.access(binary_path, os.X_OK):
            return binary_path
            
        raise RuntimeError("Failed to locate or install ttyd")
        
    except Exception as e:
        logger.error(f"Failed to set up ttyd: {e}")
        raise