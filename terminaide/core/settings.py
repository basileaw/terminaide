# terminaide/core/settings.py

"""
Configuration settings for terminaide using Pydantic models.

This module defines the configuration structure for the terminaide package,
with special handling for path management to support both root and non-root
mounting of the terminal interface.

The configuration now supports multiple script routing, allowing different
client scripts to be served on different paths. Scripts can now receive
command-line arguments through the configuration.
"""

from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Set
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

class ScriptConfig(BaseModel):
    """
    Configuration for a single terminal route.
    
    Each script configuration represents a unique terminal endpoint with its own
    script, port, and optional custom title. Scripts can now receive command-line
    arguments.
    """
    route_path: str  # The URL path where this terminal will be available
    client_script: Path  # Path to the script file to execute
    args: List[str] = Field(default_factory=list)  # Command-line arguments for the script
    port: Optional[int] = None  # Port will be auto-assigned if None
    title: Optional[str] = None  # Custom title for this terminal
    
    @field_validator('client_script')
    @classmethod
    def validate_script_path(cls, v: Union[str, Path]) -> Path:
        """Validate that the script file exists."""
        path = Path(v)
        if not path.exists():
            raise ConfigurationError(f"Script file does not exist: {path}")
        return path.absolute()
    
    @field_validator('route_path')
    @classmethod
    def validate_route_path(cls, v: str) -> str:
        """Ensure route path is properly formatted."""
        # Ensure path starts with "/"
        if not v.startswith('/'):
            v = f"/{v}"
            
        # Remove trailing slash (except for root path)
        if v != "/" and v.endswith('/'):
            v = v.rstrip('/')
            
        return v
    
    @field_validator('args')
    @classmethod
    def validate_args(cls, v: List[str]) -> List[str]:
        """Validate and normalize command-line arguments."""
        # Convert all arguments to strings to ensure consistency
        return [str(arg) for arg in v]

class TTYDConfig(BaseModel):
    """
    Main configuration for terminaide.
    
    This model handles both root ("/") and non-root ("/path") mounting configurations,
    ensuring consistent path handling throughout the application. It now supports
    multiple script configurations for different routes, including command-line arguments.
    """
    client_script: Path  # Default script (for backward compatibility)
    mount_path: str = "/"  # Default to root mounting
    port: int = Field(default=7681, gt=1024, lt=65535)  # Base port for first script
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    ttyd_options: TTYDOptions = Field(default_factory=TTYDOptions)
    template_override: Optional[Path] = None
    debug: bool = False
    title: str = "Terminal"  # Default title for the HTML template
    script_configs: List[ScriptConfig] = Field(default_factory=list)  # Multiple script configs
    
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
    
    @model_validator(mode='after')
    def validate_script_configs(self) -> 'TTYDConfig':
        """
        Ensure script configurations are valid and route paths are unique.
        Also ensure the default script is properly represented in script_configs.
        """
        # Check for duplicate route paths
        route_paths = set()
        for config in self.script_configs:
            if config.route_path in route_paths:
                raise ConfigurationError(
                    f"Duplicate route path found: {config.route_path}"
                )
            route_paths.add(config.route_path)
        
        # If no script configs but we have a default script, create one for the root
        if not self.script_configs and self.client_script:
            self.script_configs.append(
                ScriptConfig(
                    route_path="/",
                    client_script=self.client_script,
                    port=self.port,
                    title=self.title
                )
            )
        
        return self

    @property
    def is_root_mounted(self) -> bool:
        """Check if the terminal is mounted at root."""
        return self.mount_path == "/"
    
    @property
    def is_multi_script(self) -> bool:
        """Check if multiple scripts are configured."""
        return len(self.script_configs) > 1
        
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
    
    def get_script_config_for_path(self, path: str) -> Optional[ScriptConfig]:
        """
        Find the script configuration that matches a given path.
        
        Args:
            path: Request path to match
            
        Returns:
            Matching ScriptConfig or None if no match found
        """
        # For single script setup, always return the first config
        if len(self.script_configs) == 1:
            return self.script_configs[0]
        
        # In multi-script setup, find the matching route
        # Start with longest paths first to handle nested routes correctly
        sorted_configs = sorted(
            self.script_configs, 
            key=lambda c: len(c.route_path), 
            reverse=True
        )
        
        # Find the config with the longest matching route prefix
        for config in sorted_configs:
            route = config.route_path
            
            # Handle root path specially
            if route == "/" and (path == "/" or path.startswith("/terminal")):
                return config
                
            # For other routes, check if the path starts with the route
            if path.startswith(route) or path.startswith(f"{route}/terminal"):
                return config
                
        # Default to first config if no match found
        return self.script_configs[0] if self.script_configs else None
    
    def get_terminal_path_for_route(self, route_path: str) -> str:
        """
        Get the terminal path for a specific route.
        
        Args:
            route_path: The route path for a script configuration
            
        Returns:
            The terminal path for this route
        """
        if route_path == "/":
            return self.terminal_path
            
        # For non-root routes, append "/terminal"
        return f"{route_path}/terminal"

    def get_health_check_info(self) -> Dict[str, Any]:
        """Get configuration info for health checks."""
        script_info = []
        for config in self.script_configs:
            script_info.append({
                "route_path": config.route_path,
                "script": str(config.client_script),
                "args": config.args,
                "port": config.port,
                "title": config.title or self.title
            })
            
        return {
            "mount_path": self.mount_path,
            "terminal_path": self.terminal_path,
            "static_path": self.static_path,
            "is_root_mounted": self.is_root_mounted,
            "is_multi_script": self.is_multi_script,
            "port": self.port,
            "debug": self.debug,
            "max_clients": self.ttyd_options.max_clients,
            "auth_required": self.ttyd_options.credential_required,
            "script_configs": script_info
        }