# terminaide/installer.py

"""
TTYd binary and dependency installation.

This module handles the complete installation of ttyd and all its dependencies
across different platforms and environments. This updated version ensures terminaide
always uses its own internal ttyd binary without relying on system installations.

For Linux, it downloads pre-built binaries. For macOS, it compiles from source.
"""

import os
import sys
import stat
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import urllib.request

logger = logging.getLogger("terminaide")

TTYD_VERSION = "1.7.3"
TTYD_GITHUB_BASE = f"https://github.com/tsl0922/ttyd/releases/download/{TTYD_VERSION}"

# Platform-specific binary URLs
PLATFORM_BINARIES = {
    ("Linux", "x86_64"): (f"{TTYD_GITHUB_BASE}/ttyd.x86_64", "ttyd"),
    ("Linux", "aarch64"): (f"{TTYD_GITHUB_BASE}/ttyd.aarch64", "ttyd"),
    ("Linux", "arm64"): (f"{TTYD_GITHUB_BASE}/ttyd.aarch64", "ttyd"),
    # For macOS, we'll compile from source
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
    """
    Get the directory where the ttyd binary should be installed.
    
    Returns:
        Path to the bin directory within the terminaide package
    """
    package_dir = Path(__file__).parent
    bin_dir = package_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    return bin_dir

def download_binary(url: str, target_path: Path) -> None:
    """Download the ttyd binary from GitHub."""
    logger.info(f"Downloading ttyd from {url}")
    try:
        urllib.request.urlretrieve(url, target_path)
        # Make binary executable
        target_path.chmod(target_path.stat().st_mode | stat.S_IEXEC)
    except Exception as e:
        raise RuntimeError(f"Failed to download ttyd: {e}")
        
def compile_ttyd_from_source(target_path: Path) -> None:
    """
    Compile ttyd from source for macOS.
    
    This function downloads the ttyd source code, compiles it,
    and places the binary at the specified target path.
    """
    import tempfile
    import shutil
    import subprocess
    
    logger.info("Compiling ttyd from source for macOS...")
    
    # Create a temporary directory for compilation
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        source_tarball = temp_dir_path / "ttyd-source.tar.gz"
        
        # Download source code
        logger.info("Downloading ttyd source code...")
        source_url = f"https://github.com/tsl0922/ttyd/archive/refs/tags/{TTYD_VERSION}.tar.gz"
        logger.info(f"Source URL: {source_url}")
        try:
            urllib.request.urlretrieve(source_url, source_tarball)
        except Exception as e:
            raise RuntimeError(f"Failed to download ttyd source: {e}")
        
        # Extract source tarball
        logger.info("Extracting source code...")
        import tarfile
        with tarfile.open(source_tarball, "r:gz") as tar:
            tar.extractall(path=temp_dir_path)
        
        # The directory will be named "ttyd-{version}" when extracting from GitHub's tarball
        source_dir = temp_dir_path / f"ttyd-{TTYD_VERSION}"
        if not source_dir.exists():
            # Look for any ttyd-* directory as fallback
            for item in temp_dir_path.iterdir():
                if item.is_dir() and item.name.startswith("ttyd"):
                    source_dir = item
                    break
        
        if not source_dir.exists():
            raise RuntimeError("Could not find the source directory after extraction")
        
        # Create build directory
        build_dir = source_dir / "build"
        build_dir.mkdir(exist_ok=True)
        
        # Check for required dependencies
        logger.info("Checking for build dependencies...")
        required_cmds = ["cmake", "make", "cc"]
        missing_cmds = []
        
        for cmd in required_cmds:
            if not shutil.which(cmd):
                missing_cmds.append(cmd)
        
        if missing_cmds:
            raise RuntimeError(
                f"Missing required build tools: {', '.join(missing_cmds)}.\n"
                f"Please install Xcode Command Line Tools with 'xcode-select --install'\n"
                f"You may also need: brew install cmake libuv json-c libwebsockets openssl"
            )
        
        # Check for required libraries
        logger.info("Checking for required libraries...")
        try:
            # Check for libwebsockets, which is required for ttyd
            if not os.path.exists("/usr/local/opt/libwebsockets") and not os.path.exists("/opt/homebrew/opt/libwebsockets"):
                logger.warning("libwebsockets not found, attempting to install with brew")
                try:
                    subprocess.run(
                        ["brew", "install", "libwebsockets"],
                        check=True,
                        capture_output=True
                    )
                except subprocess.CalledProcessError:
                    logger.error("Failed to install libwebsockets with brew")
                    raise RuntimeError(
                        "Could not find libwebsockets, which is required for ttyd.\n"
                        "Please install it manually with: brew install libwebsockets"
                    )
                
            # Similarly check for json-c
            if not os.path.exists("/usr/local/opt/json-c") and not os.path.exists("/opt/homebrew/opt/json-c"):
                logger.warning("json-c not found, attempting to install with brew")
                try:
                    subprocess.run(
                        ["brew", "install", "json-c"],
                        check=True,
                        capture_output=True
                    )
                except subprocess.CalledProcessError:
                    logger.error("Failed to install json-c with brew")
                    raise RuntimeError(
                        "Could not find json-c, which is required for ttyd.\n"
                        "Please install it manually with: brew install json-c"
                    )
        except Exception as e:
            logger.warning(f"Could not check or install dependencies: {e}")
            logger.warning("Will attempt to build anyway, but it might fail")
        
        # Configure and build
        logger.info("Configuring build...")
        try:
            # Change to build directory
            os.chdir(build_dir)
            
            # Run cmake with hints to find dependencies
            brew_prefix = None
            try:
                brew_prefix = subprocess.check_output(["brew", "--prefix"], text=True).strip()
                logger.info(f"Homebrew prefix: {brew_prefix}")
            except (subprocess.SubprocessError, FileNotFoundError):
                logger.warning("Homebrew not found or error running brew --prefix")
                
            cmake_args = ["cmake", ".."]
            
            # Add hint paths for libraries if Homebrew is available
            if brew_prefix:
                cmake_args.extend([
                    f"-DCMAKE_PREFIX_PATH={brew_prefix}",
                    f"-DOPENSSL_ROOT_DIR={brew_prefix}/opt/openssl"
                ])
                
            logger.info(f"Running CMake with: {' '.join(cmake_args)}")
            subprocess.run(
                cmake_args,
                check=True,
                capture_output=True,
                text=True
            )
            
            # Run make
            logger.info("Building ttyd...")
            subprocess.run(
                ["make"],
                check=True, 
                capture_output=True,
                text=True
            )
            
            # Check if the binary was built successfully
            binary_path = build_dir / "ttyd"
            if not binary_path.exists():
                raise RuntimeError("ttyd binary was not created after build")
            
            # Copy the binary to the target path
            shutil.copy2(binary_path, target_path)
            target_path.chmod(target_path.stat().st_mode | stat.S_IEXEC)
            
            logger.info(f"Successfully compiled ttyd and installed to {target_path}")
            
        except subprocess.CalledProcessError as e:
            error_output = e.stderr
            raise RuntimeError(f"Build failed: {error_output}")
        except Exception as e:
            raise RuntimeError(f"Error during build process: {e}")

def get_ttyd_path(force_reinstall: bool = False) -> Optional[Path]:
    """
    Get path to installed ttyd binary, installing if necessary.
    
    Args:
        force_reinstall: If True, reinstall ttyd even if it exists
    
    Returns:
        Path to the ttyd binary
    """
    system, machine = get_platform_info()
    platform_key = (system, machine)
    binary_dir = get_binary_dir()
    binary_name = "ttyd"
    binary_path = binary_dir / binary_name
    
    # Handle macOS specially - we'll compile from source
    if system == "Darwin":
        logger.info("macOS detected - ttyd will be compiled from source")
        
        # Check if binary exists and is executable, skip if not force_reinstall
        if not force_reinstall and binary_path.exists() and os.access(binary_path, os.X_OK):
            logger.info(f"Using existing ttyd binary at {binary_path}")
            return binary_path
        
        # Compile from source for macOS
        try:
            compile_ttyd_from_source(binary_path)
            return binary_path
        except Exception as e:
            logger.error(f"Error compiling ttyd from source: {e}")
            raise RuntimeError(f"Failed to compile ttyd for macOS: {e}")
    
    # For other platforms, continue with binary download approach
    # Try common platform keys for Linux
    if platform_key not in PLATFORM_BINARIES:
        if system == "Linux":
            for machine_type in ["arm64", "aarch64", "x86_64"]:
                alt_key = (system, machine_type)
                if alt_key in PLATFORM_BINARIES:
                    platform_key = alt_key
                    break
    
    if platform_key not in PLATFORM_BINARIES:
        raise PlatformNotSupportedError(system, machine)

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
    
    url, download_binary_name = PLATFORM_BINARIES[platform_key]
    
    # Check if binary exists and is executable, or if force_reinstall is specified
    if force_reinstall or not binary_path.exists() or not os.access(binary_path, os.X_OK):
        download_binary(url, binary_path)
    
    return binary_path

def setup_ttyd(force_reinstall: bool = None) -> Path:
    """
    Ensure ttyd is installed and return its path.
    
    This is the main entry point for the installer module.
    
    Args:
        force_reinstall: If True, reinstall ttyd even if it exists.
                         If None, check TERMINAIDE_FORCE_REINSTALL env var.
    
    Returns:
        Path to the ttyd binary
    """
    # Check environment variable if force_reinstall not specified
    if force_reinstall is None:
        force_reinstall = os.environ.get("TERMINAIDE_FORCE_REINSTALL", "").lower() in ("1", "true", "yes")
    
    try:
        # Get our managed version
        binary_path = get_ttyd_path(force_reinstall)
        if binary_path and os.access(binary_path, os.X_OK):
            return binary_path
            
        raise RuntimeError("Failed to locate or install ttyd")
        
    except Exception as e:
        logger.error(f"Failed to set up ttyd: {e}")
        raise

class PlatformNotSupportedError(RuntimeError):
    """Raised when trying to install on an unsupported platform."""
    def __init__(self, system: str, machine: str):
        message = (
            f"Platform not supported: {system} {machine}\n"
            f"Terminaide currently supports: Linux x86_64, Linux ARM64, macOS.\n"
            f"Please file an issue if you need support for other platforms."
        )
        super().__init__(message)
        self.system = system
        self.machine = machine