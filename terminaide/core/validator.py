# reload_validator.py

"""
Configuration validation utilities for hot reload scenarios.

This module provides pre-validation and graceful handling of configuration
changes during hot reload to prevent server crashes.
"""

import logging
from pathlib import Path
from typing import List, Tuple, Any
from dataclasses import dataclass

from .models import ScriptConfig

logger = logging.getLogger("terminaide")


@dataclass
class ValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        self.errors = self.errors or []
        self.warnings = self.warnings or []


class ReloadValidator:
    """Validates configuration changes for hot reload scenarios."""
    
    @staticmethod
    def validate_script_config(
        script_config: ScriptConfig, 
        is_reload: bool = False
    ) -> ValidationResult:
        """Validate a single script configuration.
        
        Args:
            script_config: The script configuration to validate
            is_reload: Whether this is a hot reload scenario
            
        Returns:
            ValidationResult with any errors or warnings
        """
        result = ValidationResult(is_valid=True)
        
        # For function-based routes, we don't need to validate script paths
        if script_config.is_function_based:
            return result
            
        # Check script path
        if script_config.script:
            script_path = Path(script_config.script)
            if not script_path.exists():
                message = f"Script not found: {script_path}"
                if is_reload:
                    # During reload, missing scripts are warnings, not errors
                    result.warnings.append(message)
                    logger.warning(f"Hot reload warning: {message}")
                else:
                    # During initial startup, missing scripts are errors
                    result.errors.append(message)
                    result.is_valid = False
                    
        return result
    
    @classmethod
    def pre_validate_config(
        cls, 
        config: Any,  # TerminaideConfig
        is_reload: bool = False
    ) -> ValidationResult:
        """Pre-validate configuration before server startup/reload.
        
        Args:
            config: The configuration to validate
            is_reload: Whether this is a hot reload scenario
            
        Returns:
            ValidationResult with aggregated errors and warnings
        """
        result = ValidationResult(is_valid=True)
        
        # Validate terminal routes if present
        if hasattr(config, '_target') and isinstance(config._target, list):
            for route_config in config._target:
                if isinstance(route_config, ScriptConfig):
                    route_result = cls.validate_script_config(
                        route_config, 
                        is_reload=is_reload
                    )
                    result.errors.extend(route_result.errors)
                    result.warnings.extend(route_result.warnings)
                    if not route_result.is_valid:
                        result.is_valid = False
                        
        return result
    
    @staticmethod
    def create_fallback_config(
        original_config: ScriptConfig,
        error_message: str
    ) -> ScriptConfig:
        """Create a fallback configuration for a failed route.
        
        Args:
            original_config: The original configuration that failed
            error_message: The error message to display
            
        Returns:
            A new ScriptConfig that displays the error
        """
        # Create a temporary error script
        from tempfile import NamedTemporaryFile
        import textwrap
        
        error_script = textwrap.dedent(f'''
            #!/usr/bin/env python3
            # Error fallback script
            
            print("\\033[91m✗ Route Configuration Error\\033[0m")
            print()
            print("Route: {original_config.route_path}")
            print("Error: {error_message}")
            print()
            print("This route is temporarily unavailable due to a configuration error.")
            print("Please check your server logs for more details.")
        ''')
        
        # Create temporary file
        with NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(error_script)
            temp_path = Path(f.name)
            
        # Create fallback config
        fallback = ScriptConfig(
            script=temp_path,
            route_path=original_config.route_path,
            title=f"Error: {original_config.title or original_config.route_path}",
            port=original_config.port,
            args=[]
        )
        
        return fallback


def validate_and_recover_routes(
    route_configs: List[ScriptConfig],
    is_reload: bool = False
) -> Tuple[List[ScriptConfig], List[str]]:
    """Validate routes and provide fallbacks for failed ones.
    
    Args:
        route_configs: List of route configurations to validate
        is_reload: Whether this is a hot reload scenario
        
    Returns:
        Tuple of (processed_routes, error_messages)
    """
    validator = ReloadValidator()
    processed_routes = []
    error_messages = []
    
    for route_config in route_configs:
        result = validator.validate_script_config(route_config, is_reload=is_reload)
        
        if result.is_valid or (is_reload and not result.errors):
            # Route is valid or only has warnings during reload
            processed_routes.append(route_config)
            for warning in result.warnings:
                logger.warning(f"Route {route_config.route_path}: {warning}")
        else:
            # Route has errors - create fallback
            error_msg = "; ".join(result.errors)
            error_messages.append(f"Route {route_config.route_path}: {error_msg}")
            
            if is_reload:
                # During reload, provide a fallback route
                fallback = validator.create_fallback_config(route_config, error_msg)
                processed_routes.append(fallback)
                logger.error(f"Created fallback for failed route {route_config.route_path}: {error_msg}")
            else:
                # During initial startup, skip the route
                logger.error(f"Skipping invalid route {route_config.route_path}: {error_msg}")
                
    return processed_routes, error_messages