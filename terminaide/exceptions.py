# terminaide/exceptions.py

"""
Custom exceptions for the terminaide package.

These exceptions provide specific error cases that may occur during
ttyd setup, installation, and operation.
"""

from typing import Optional
from pathlib import Path

class terminaideError(Exception):
    """Base exception for all terminaide errors."""

class BinaryError(terminaideError):
    """Base class for binary-related errors."""
    def __init__(self, message: str, binary_path: Optional[Path] = None):
        super().__init__(message)
        self.binary_path = binary_path

class InstallationError(BinaryError):
    """Raised when ttyd binary installation fails."""
    def __init__(
        self, 
        message: str, 
        binary_path: Optional[Path] = None,
        platform: Optional[str] = None
    ):
        super().__init__(
            f"Installation failed: {message}" +
            (f" (platform: {platform})" if platform else ""),
            binary_path
        )
        self.platform = platform

class PlatformNotSupportedError(InstallationError):
    """Raised when trying to install on an unsupported platform."""
    def __init__(self, system: str, machine: str):
        super().__init__(
            f"Platform not supported: {system} {machine}",
            platform=f"{system} {machine}"
        )
        self.system = system
        self.machine = machine

class DependencyError(InstallationError):
    """Raised when required system dependencies are missing."""
    def __init__(self, missing_deps: list[str]):
        deps_str = ", ".join(missing_deps)
        super().__init__(
            f"Missing required dependencies: {deps_str}\n"
            "Please install:\n"
            "  Ubuntu/Debian: apt-get install libwebsockets-dev libjson-c-dev\n"
            "  MacOS: brew install libwebsockets json-c"
        )
        self.missing_deps = missing_deps

class DownloadError(InstallationError):
    """Raised when downloading the ttyd binary fails."""
    def __init__(self, url: str, error: str):
        super().__init__(f"Failed to download from {url}: {error}")
        self.url = url
        self.error = error

class TTYDStartupError(BinaryError):
    """Raised when ttyd process fails to start."""
    def __init__(
        self, 
        message: str = None, 
        stderr: str = None,
        binary_path: Optional[Path] = None
    ):
        msg = message or "Failed to start ttyd process"
        if stderr:
            msg = f"{msg}\nttyd error output:\n{stderr}"
        super().__init__(msg, binary_path)
        self.stderr = stderr

class TTYDProcessError(BinaryError):
    """Raised when ttyd process encounters an error during operation."""
    def __init__(
        self, 
        message: str = None, 
        exit_code: int = None,
        binary_path: Optional[Path] = None
    ):
        msg = message or "ttyd process error"
        if exit_code is not None:
            msg = f"{msg} (exit code: {exit_code})"
        super().__init__(msg, binary_path)
        self.exit_code = exit_code

class ClientScriptError(terminaideError):
    """Raised when there are issues with the client script."""
    def __init__(self, script_path: str, message: str = None):
        super().__init__(
            f"Error with client script '{script_path}': {message or 'Unknown error'}"
        )
        self.script_path = script_path

class TemplateError(terminaideError):
    """Raised when there are issues with the HTML template."""
    def __init__(self, template_path: str = None, message: str = None):
        msg = "Template error"
        if template_path:
            msg = f"{msg} with '{template_path}'"
        if message:
            msg = f"{msg}: {message}"
        super().__init__(msg)
        self.template_path = template_path

class ProxyError(terminaideError):
    """Raised when there are issues with the proxy configuration or operation."""
    def __init__(self, message: str = None, original_error: Exception = None):
        msg = message or "Proxy error"
        if original_error:
            msg = f"{msg}: {str(original_error)}"
        super().__init__(msg)
        self.original_error = original_error

class ConfigurationError(terminaideError):
    """Raised when there are issues with the provided configuration."""
    def __init__(self, message: str, field: str = None):
        msg = f"Configuration error"
        if field:
            msg = f"{msg} in '{field}'"
        msg = f"{msg}: {message}"
        super().__init__(msg)
        self.field = field