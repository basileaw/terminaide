# terminaide/core/settings.py

"""
Configuration settings for terminaide using Pydantic models.

This module defines the configuration structure for the terminaide package,
with special handling for path management to support both root and non-root
mounting of the terminal interface.
"""

from pathlib import Path
from typing import Dict, Any, Optional, Union
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    AnyHttpUrl
)

from ..exceptions import ConfigurationError

class TTYDOptions(BaseModel):
    """TTYd process-specific configuration options."""
    writable: bool = True
    port: int = Field(default=7681, gt=1024, lt=65535)
    interface: str = "127.0.0.1"  # Listen only on localhost for security
    check_origin: bool = True
    max_clients: int = Field(default=1, gt=0)
    credential_required: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    
    @model_validator(mode='after')
    def validate_credentials(self) -> 'TTYDOptions':
        """Ensure both username and password are provided if authentication is enabled."""
        if self.credential_required:
            if not (self.username and self.password):
                raise ConfigurationError(
                    "Both username and password must be provided when credential_required is True"
                )
        return self

class ThemeConfig(BaseModel):
    """Terminal theme configuration."""
    background: str = "black"
    foreground: str = "white"
    cursor: str = "white"
    cursor_accent: Optional[str] = None
    selection: Optional[str] = None
    font_family: Optional[str] = None
    font_size: Optional[int] = Field(default=None, gt=0)

class TTYDConfig(BaseModel):
    """
    Main configuration for terminaide.
    
    This model handles both root ("/") and non-root ("/path") mounting configurations,
    ensuring consistent path handling throughout the application.
    """
    client_script: Path
    mount_path: str = "/"  # Default to root mounting
    port: int = Field(default=7681, gt=1024, lt=65535)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    ttyd_options: TTYDOptions = Field(default_factory=TTYDOptions)
    template_override: Optional[Path] = None
    debug: bool = False
    
    @field_validator('client_script', 'template_override')
    @classmethod
    def validate_paths(cls, v: Optional[Union[str, Path]]) -> Optional[Path]:
        """Validate that provided paths exist."""
        if v is None:
            return None
        
        path = Path(v)
        if not path.exists():
            raise ConfigurationError(f"Path does not exist: {path}")
        return path.absolute()
    
    @field_validator('mount_path')
    @classmethod
    def validate_mount_path(cls, v: str) -> str:
        """
        Ensure mount path is properly formatted.
        
        For root mounting ("/"):
        - Accepts "/" or "" and normalizes to "/"
        
        For non-root mounting:
        - Ensures path starts with "/"
        - Removes trailing "/"
        - Does not allow "/terminal" as it's reserved
        """
        # Handle root mounting
        if v in ("", "/"):
            return "/"
            
        # Ensure path starts with "/"
        if not v.startswith('/'):
            v = f"/{v}"
            
        # Remove trailing slash
        v = v.rstrip('/')
        
        # Prevent mounting at /terminal as it's reserved for ttyd
        if v == "/terminal":
            raise ConfigurationError(
                '"/terminal" is reserved for ttyd connections. '
                'Please choose a different mount path.'
            )
            
        return v

    @property
    def is_root_mounted(self) -> bool:
        """Check if the terminal is mounted at root."""
        return self.mount_path == "/"
        
    @property
    def terminal_path(self) -> str:
        """
        Get the path where ttyd terminal is mounted.
        
        For root mounting ("/"):
            terminal_path = "/terminal"
        For non-root mounting ("/path"):
            terminal_path = "/path/terminal"
        """
        if self.is_root_mounted:
            return "/terminal"
        return f"{self.mount_path}/terminal"
        
    @property
    def static_path(self) -> str:
        """
        Get the path where static files are served.
        
        For root mounting ("/"):
            static_path = "/static"
        For non-root mounting ("/path"):
            static_path = "/path/static"
        """
        if self.is_root_mounted:
            return "/static"
        return f"{self.mount_path}/static"

    def get_health_check_info(self) -> Dict[str, Any]:
        """Get configuration info for health checks."""
        return {
            "mount_path": self.mount_path,
            "terminal_path": self.terminal_path,
            "static_path": self.static_path,
            "is_root_mounted": self.is_root_mounted,
            "port": self.port,
            "debug": self.debug,
            "max_clients": self.ttyd_options.max_clients,
            "auth_required": self.ttyd_options.credential_required
        }