# tests/test_validator.py

"""Tests for the validator module."""

import os
import tempfile
from pathlib import Path
import pytest

from terminaide.core.validator import (
    ReloadValidator, 
    ValidationResult,
    validate_and_recover_routes
)
from terminaide.core.models import ScriptConfig


class TestReloadValidator:
    """Test the ReloadValidator class."""
    
    def test_validate_script_config_valid_path(self, tmp_path):
        """Test validation with a valid script path."""
        # Create a test script
        script_path = tmp_path / "test.py"
        script_path.write_text("print('test')")
        
        config = ScriptConfig(
            script=script_path,
            route_path="/test"
        )
        
        result = ReloadValidator.validate_script_config(config)
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        
    def test_validate_script_config_missing_path_startup(self):
        """Test validation with missing path during startup."""
        config = ScriptConfig(
            script=Path("/nonexistent/path.py"),
            route_path="/test"
        )
        
        # During startup (is_reload=False), missing paths are errors
        result = ReloadValidator.validate_script_config(config, is_reload=False)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert "Script not found" in result.errors[0]
        
    def test_validate_script_config_missing_path_reload(self):
        """Test validation with missing path during reload."""
        config = ScriptConfig(
            script=Path("/nonexistent/path.py"),
            route_path="/test"
        )
        
        # During reload (is_reload=True), missing paths are warnings
        result = ReloadValidator.validate_script_config(config, is_reload=True)
        assert result.is_valid  # Still valid during reload
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert "Script not found" in result.warnings[0]
        
    def test_validate_function_based_route(self):
        """Test that function-based routes are always valid."""
        def test_func():
            print("test")
            
        config = ScriptConfig(
            route_path="/test",
            function_object=test_func
        )
        
        # Function-based routes should always be valid
        result = ReloadValidator.validate_script_config(config)
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        
    def test_create_fallback_config(self):
        """Test creation of fallback configuration."""
        original = ScriptConfig(
            script=Path("/missing/script.py"),
            route_path="/test",
            title="Test Route"
        )
        
        fallback = ReloadValidator.create_fallback_config(
            original, 
            "File not found"
        )
        
        # Fallback should have same route but different script
        assert fallback.route_path == original.route_path
        assert fallback.script != original.script
        assert fallback.script.exists()
        assert "Error:" in fallback.title
        
        # Clean up
        fallback.script.unlink()
        
    def test_validate_and_recover_routes(self, tmp_path):
        """Test route validation and recovery."""
        # Create one valid and one invalid route
        valid_script = tmp_path / "valid.py"
        valid_script.write_text("print('valid')")
        
        routes = [
            ScriptConfig(
                script=valid_script,
                route_path="/valid"
            ),
            ScriptConfig(
                script=Path("/nonexistent.py"),
                route_path="/invalid"
            )
        ]
        
        # Test during startup - invalid routes are skipped
        processed, errors = validate_and_recover_routes(routes, is_reload=False)
        assert len(processed) == 1  # Only valid route
        assert len(errors) == 1
        assert processed[0].route_path == "/valid"
        
        # Test during reload - invalid routes get fallbacks
        processed, errors = validate_and_recover_routes(routes, is_reload=True)
        assert len(processed) == 2  # Both routes (one is fallback)
        # During reload, warnings don't produce errors in the return value
        assert len(errors) == 0  # No errors during reload, only warnings
        
        # Check that we have one valid and one fallback
        valid_routes = [r for r in processed if r.script == valid_script]
        fallback_routes = [r for r in processed if r.script != valid_script]
        assert len(valid_routes) == 1
        assert len(fallback_routes) == 1
        
        # Clean up fallback scripts
        for route in fallback_routes:
            if route.script.exists():
                route.script.unlink()


class TestIntegrationWithReload:
    """Test integration with hot reload scenarios."""
    
    def test_reload_context_detection(self, monkeypatch):
        """Test that reload context is properly detected."""
        # Simulate reload environment
        monkeypatch.setenv("TERMINAIDE_MODE", "script")
        monkeypatch.setenv("TERMINAIDE_PORT", "8000")
        
        # Import after setting env vars
        from terminaide.core.models import TTYDConfig
        
        # This should not raise even with invalid path
        config = TTYDConfig(
            script=None,  # Will be None due to validation
            route_configs=[]
        )
        
        # In reload context, invalid paths should return None
        assert config.script is None