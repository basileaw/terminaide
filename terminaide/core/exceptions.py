# core/exceptions.py

"""
Custom exceptions for the terminaide package.

These exceptions provide specific error cases that may occur during
ttyd setup, installation, and operation. The exception hierarchy has been
expanded to support multi-terminal (apps-server) routing scenarios.
"""

from typing import Optional, List
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
        binary_path: Optional[Path] = None,
        route_path: Optional[str] = None
    ):
        route_info = f" for route '{route_path}'" if route_path else ""
        msg = message or f"Failed to start ttyd process{route_info}"
        if stderr:
            msg = f"{msg}\nttyd error output:\n{stderr}"
        super().__init__(msg, binary_path)
        self.stderr = stderr
        self.route_path = route_path

class TTYDProcessError(BinaryError):
    """Raised when ttyd process encounters an error during operation."""
    def __init__(
        self, 
        message: str = None, 
        exit_code: int = None,
        binary_path: Optional[Path] = None,
        route_path: Optional[str] = None
    ):
        route_info = f" for route '{route_path}'" if route_path else ""
        msg = message or f"ttyd process error{route_info}"
        if exit_code is not None:
            msg = f"{msg} (exit code: {exit_code})"
        super().__init__(msg, binary_path)
        self.exit_code = exit_code
        self.route_path = route_path

class ClientScriptError(terminaideError):
    """Raised when there are issues with the client script."""
    def __init__(self, script_path: str, message: str = None, route_path: Optional[str] = None):
        route_info = f" for route '{route_path}'" if route_path else ""
        super().__init__(
            f"Error with client script '{script_path}'{route_info}: {message or 'Unknown error'}"
        )
        self.script_path = script_path
        self.route_path = route_path

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
    def __init__(self, message: str = None, original_error: Exception = None, route_path: Optional[str] = None):
        route_info = f" for route '{route_path}'" if route_path else ""
        msg = (message or "Proxy error") + route_info
        if original_error:
            msg = f"{msg}: {str(original_error)}"
        super().__init__(msg)
        self.original_error = original_error
        self.route_path = route_path

class ConfigurationError(terminaideError):
    """Raised when there are issues with the provided configuration."""
    def __init__(self, message: str, field: str = None):
        msg = f"Configuration error"
        if field:
            msg = f"{msg} in '{field}'"
        msg = f"{msg}: {message}"
        super().__init__(msg)
        self.field = field

# --- New Exceptions for Multi-Script Support ---

class RouteNotFoundError(ProxyError):
    """Raised when a request cannot be routed to any known script configuration."""
    def __init__(self, message: str, request_path: Optional[str] = None):
        path_info = f" (request path: {request_path})" if request_path else ""
        super().__init__(f"Route not found: {message}{path_info}")
        self.request_path = request_path

class PortAllocationError(ConfigurationError):
    """Raised when port allocation fails for multi-terminal (apps-server) configuration."""
    def __init__(self, message: str, attempted_ports: Optional[List[int]] = None):
        port_info = f" (attempted ports: {attempted_ports})" if attempted_ports else ""
        super().__init__(f"{message}{port_info}", field="port")
        self.attempted_ports = attempted_ports

class ScriptConfigurationError(ConfigurationError):
    """Raised when there are issues with script configurations."""
    def __init__(self, message: str, route_path: Optional[str] = None):
        field = f"terminal_routes[{route_path}]" if route_path else "terminal_routes"
        super().__init__(message, field=field)
        self.route_path = route_path

class DuplicateRouteError(ScriptConfigurationError):
    """Raised when duplicate route paths are found in script configurations."""
    def __init__(self, route_path: str):
        super().__init__(
            f"Duplicate route path: {route_path}",
            route_path=route_path
        )