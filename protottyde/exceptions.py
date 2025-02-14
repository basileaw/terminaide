# protottyde/exceptions.py

"""
Custom exceptions for the protottyde package.

These exceptions provide specific error cases that may occur during
ttyd setup and operation.
"""

class ProtottydeError(Exception):
    """Base exception for all protottyde errors."""

class TTYDNotFoundError(ProtottydeError):
    """Raised when ttyd is not installed or not found in PATH."""
    def __init__(self, message: str = None):
        super().__init__(
            message or 
            "ttyd not found. Install with:\n"
            "  Ubuntu/Debian: apt-get install ttyd\n"
            "  MacOS: brew install ttyd\n"
            "  Or build from source: https://github.com/tsl0922/ttyd"
        )

class TTYDStartupError(ProtottydeError):
    """Raised when ttyd process fails to start."""
    def __init__(self, message: str = None, stderr: str = None):
        msg = message or "Failed to start ttyd process"
        if stderr:
            msg = f"{msg}\nttyd error output:\n{stderr}"
        super().__init__(msg)
        self.stderr = stderr

class TTYDProcessError(ProtottydeError):
    """Raised when ttyd process encounters an error during operation."""
    def __init__(self, message: str = None, exit_code: int = None):
        msg = message or "ttyd process error"
        if exit_code is not None:
            msg = f"{msg} (exit code: {exit_code})"
        super().__init__(msg)
        self.exit_code = exit_code

class ClientScriptError(ProtottydeError):
    """Raised when there are issues with the client script."""
    def __init__(self, script_path: str, message: str = None):
        super().__init__(
            f"Error with client script '{script_path}': {message or 'Unknown error'}"
        )
        self.script_path = script_path

class TemplateError(ProtottydeError):
    """Raised when there are issues with the HTML template."""
    def __init__(self, template_path: str = None, message: str = None):
        msg = "Template error"
        if template_path:
            msg = f"{msg} with '{template_path}'"
        if message:
            msg = f"{msg}: {message}"
        super().__init__(msg)
        self.template_path = template_path

class ProxyError(ProtottydeError):
    """Raised when there are issues with the proxy configuration or operation."""
    def __init__(self, message: str = None, original_error: Exception = None):
        msg = message or "Proxy error"
        if original_error:
            msg = f"{msg}: {str(original_error)}"
        super().__init__(msg)
        self.original_error = original_error

class ConfigurationError(ProtottydeError):
    """Raised when there are issues with the provided configuration."""
    def __init__(self, message: str, field: str = None):
        msg = f"Configuration error"
        if field:
            msg = f"{msg} in '{field}'"
        msg = f"{msg}: {message}"
        super().__init__(msg)
        self.field = field