# protottyde/core/settings.py

"""
Configuration settings for protottyde using Pydantic models.
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
    interface: str = "0.0.0.0"
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
    """Main configuration for protottyde."""
    client_script: Path
    mount_path: str = "/tty"
    port: int = Field(default=7681, gt=1024, lt=65535)
    theme: ThemeConfig
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
        """Ensure mount path starts with / and doesn't end with /."""
        if not v.startswith('/'):
            v = f"/{v}"
        return v.rstrip('/')

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TTYDConfig':
        """Create config from a dictionary, with proper error handling."""
        try:
            return cls(**data)
        except Exception as e:
            raise ConfigurationError(str(e))

    def to_ttyd_args(self) -> list[str]:
        """Convert configuration to ttyd command line arguments."""
        args = []
        
        # Add standard options
        args.extend(['-p', str(self.ttyd_options.port)])
        args.extend(['-i', self.ttyd_options.interface])
        
        if not self.ttyd_options.check_origin:
            args.append('--no-check-origin')
        
        if self.ttyd_options.credential_required:
            args.extend([
                '-c', 
                f"{self.ttyd_options.username}:{self.ttyd_options.password}"
            ])
        
        # Add theme configuration
        theme_json = self.theme.model_dump_json()
        args.extend(['-t', f'theme={theme_json}'])
        
        if not self.ttyd_options.writable:
            args.append('-R')
        
        return args

    def get_health_check_info(self) -> Dict[str, Any]:
        """Get configuration info for health checks."""
        return {
            "mount_path": self.mount_path,
            "port": self.port,
            "debug": self.debug,
            "max_clients": self.ttyd_options.max_clients,
            "auth_required": self.ttyd_options.credential_required
        }