# protottyde/installer.py

"""
TTYd binary and dependency installation.

This module handles the complete installation of ttyd and all its dependencies
across different platforms and environments.
"""

import os
import sys
import stat
import shutil
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import urllib.request

logger = logging.getLogger("protottyde")

TTYD_VERSION = "1.7.3"
TTYD_GITHUB_BASE = f"https://github.com/tsl0922/ttyd/releases/download/{TTYD_VERSION}"

# Platform-specific binary URLs
PLATFORM_BINARIES = {
    ("Linux", "x86_64"): (f"{TTYD_GITHUB_BASE}/ttyd.x86_64", "ttyd"),
    ("Linux", "aarch64"): (f"{TTYD_GITHUB_BASE}/ttyd.aarch64", "ttyd"),
    ("Linux", "arm64"): (f"{TTYD_GITHUB_BASE}/ttyd.aarch64", "ttyd"),
    ("Darwin", "arm64"): (f"{TTYD_GITHUB_BASE}/ttyd.darwin.arm64", "ttyd"),
}

# Platform-specific system dependencies
SYSTEM_DEPENDENCIES = {
    "apt": {
        "packages": ["libwebsockets-dev", "libjson-c-dev"],
        "libraries": ["libwebsockets.so", "libjson-c.so"]
    },
    "brew": {
        "packages": ["libwebsockets", "json-c"],
        "libraries": ["libwebsockets.dylib", "libjson-c.dylib"]
    }
}

def get_package_manager() -> Optional[str]:
    """Detect the system's package manager."""
    if platform.system() == "Darwin":
        try:
            subprocess.check_output(["brew", "--version"])
            return "brew"
        except (subprocess.SubprocessError, FileNotFoundError):
            return None
    elif platform.system() == "Linux":
        try:
            subprocess.check_output(["apt-get", "--version"])
            return "apt"
        except (subprocess.SubprocessError, FileNotFoundError):
            return None
    return None

def install_system_dependencies(package_manager: str) -> None:
    """Install required system dependencies using the appropriate package manager."""
    deps = SYSTEM_DEPENDENCIES.get(package_manager)
    if not deps:
        raise RuntimeError(f"No dependency information for package manager: {package_manager}")

    logger.info(f"Installing system dependencies using {package_manager}...")
    
    try:
        if package_manager == "apt":
            # Check if we can use sudo
            try:
                subprocess.check_output(["sudo", "-n", "true"])
                sudo_prefix = ["sudo"]
            except (subprocess.SubprocessError, FileNotFoundError):
                sudo_prefix = []

            # Update package list
            subprocess.run(
                [*sudo_prefix, "apt-get", "update", "-y"],
                check=True,
                capture_output=True
            )
            
            # Install packages
            subprocess.run(
                [*sudo_prefix, "apt-get", "install", "-y", *deps["packages"]],
                check=True,
                capture_output=True
            )
            
        elif package_manager == "brew":
            for pkg in deps["packages"]:
                subprocess.run(
                    ["brew", "install", pkg],
                    check=True,
                    capture_output=True
                )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to install system dependencies using {package_manager}. "
            f"Error: {e.stderr.decode() if e.stderr else str(e)}"
        )

def verify_system_libraries(package_manager: str) -> List[str]:
    """Verify required system libraries are present and return any missing ones."""
    deps = SYSTEM_DEPENDENCIES.get(package_manager)
    if not deps:
        raise RuntimeError(f"No dependency information for package manager: {package_manager}")

    missing = []
    if package_manager == "apt":
        try:
            output = subprocess.check_output(["ldconfig", "-p"]).decode()
            missing = [lib for lib in deps["libraries"] if lib not in output]
        except subprocess.SubprocessError:
            logger.warning("Could not verify libraries with ldconfig")
    elif package_manager == "brew":
        brew_prefix = subprocess.check_output(["brew", "--prefix"]).decode().strip()
        lib_path = Path(brew_prefix) / "lib"
        missing = [
            lib for lib in deps["libraries"] 
            if not (lib_path / lib).exists()
        ]
    
    return missing

def get_platform_info() -> Tuple[str, str]:
    """Get current platform and architecture."""
    system = platform.system()
    machine = platform.machine().lower()
    
    # Normalize ARM architecture names
    if machine in ["arm64", "aarch64"]:
        machine = "arm64"
    
    return system, machine

def get_binary_dir() -> Path:
    """Get the directory where the ttyd binary should be installed."""
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

def get_ttyd_path() -> Optional[Path]:
    """Get path to installed ttyd binary, installing if necessary."""
    system, machine = get_platform_info()
    platform_key = (system, machine)
    
    # Try common platform keys
    if platform_key not in PLATFORM_BINARIES:
        # For Linux, try to map to a compatible architecture
        if system == "Linux":
            for machine_type in ["arm64", "aarch64", "x86_64"]:
                alt_key = (system, machine_type)
                if alt_key in PLATFORM_BINARIES:
                    platform_key = alt_key
                    break
    
    if platform_key not in PLATFORM_BINARIES:
        raise RuntimeError(
            f"Unsupported platform: {system} {machine}. "
            "Please report this issue on GitHub."
        )

    # Set up system dependencies first
    package_manager = get_package_manager()
    if not package_manager:
        raise RuntimeError(
            f"No supported package manager found for {system}. "
            "Please install libwebsockets and json-c manually."
        )

    # Check for missing libraries
    missing_libs = verify_system_libraries(package_manager)
    if missing_libs:
        install_system_dependencies(package_manager)
        # Verify installation succeeded
        still_missing = verify_system_libraries(package_manager)
        if still_missing:
            raise RuntimeError(
                f"Failed to install required libraries: {', '.join(still_missing)}"
            )
    
    url, binary_name = PLATFORM_BINARIES[platform_key]
    binary_dir = get_binary_dir()
    binary_path = binary_dir / binary_name
    
    # Check if binary exists and is executable
    if not binary_path.exists() or not os.access(binary_path, os.X_OK):
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