# terminaide/core/route_colors.py

import sys
import hashlib
from typing import Dict, Optional
from pathlib import Path

class RouteColorManager:
    """Manages consistent color assignments and formatting for routes."""
    
    # Bright, distinguishable colors for route titles
    ROUTE_COLORS = [
        "\033[94m",   # Bright Blue
        "\033[95m",   # Bright Magenta
        "\033[96m",   # Bright Cyan
        "\033[93m",   # Bright Yellow
        "\033[91m",   # Bright Red
        "\033[92m",   # Bright Green
        "\033[97m",   # Bright White
        "\033[35m",   # Magenta
        "\033[34m",   # Blue
        "\033[36m",   # Cyan
        "\033[33m",   # Yellow
        "\033[31m",   # Red
        "\033[32m",   # Green
        "\033[37m",   # White
        "\033[90m",   # Bright Black (Gray)
        "\033[38;5;208m",  # Orange
        "\033[38;5;165m",  # Pink
        "\033[38;5;51m",   # Light Cyan
        "\033[38;5;226m",  # Light Yellow
        "\033[38;5;46m",   # Light Green
    ]
    
    RESET = "\033[0m"
    
    def __init__(self):
        self._route_colors: Dict[str, str] = {}
        self._color_enabled = sys.stdout.isatty()
    
    def get_route_color(self, route_path: str) -> str:
        """Get a consistent color for a route based on its path."""
        if not self._color_enabled:
            return ""
            
        if route_path not in self._route_colors:
            # Use hash to get consistent color assignment
            hash_value = int(hashlib.md5(route_path.encode()).hexdigest()[:8], 16)
            color_index = hash_value % len(self.ROUTE_COLORS)
            self._route_colors[route_path] = self.ROUTE_COLORS[color_index]
        
        return self._route_colors[route_path]
    
    def colorize_title(self, title: str, route_path: str) -> str:
        """Colorize a route title with its assigned color."""
        if not self._color_enabled:
            return title
        color = self.get_route_color(route_path)
        return f"{color}{title}{self.RESET}"
    
    def format_route_info(self, route_path: str, title: str, script_config, port: Optional[int] = None, pid: Optional[int] = None) -> tuple[str, str]:
        """Create a standardized route info string with consistent formatting.
        
        Returns:
            tuple: (main_line, script_line) for separate logging
        """
        colored_title = self.colorize_title(title, route_path)
        route_type = "function" if script_config.is_function_based else "script"
        
        # Format the main info line
        info_parts = [
            f"'{colored_title}'",
            f"({route_type})",
            f"route: {route_path}"
        ]
        
        if port:
            info_parts.append(f"port: {port}")
        if pid:
            info_parts.append(f"pid: {pid}")
            
        main_line = " | ".join(info_parts) + " ⤸"
        
        # Format the script path line
        script_info = str(script_config.effective_script_path) if script_config.effective_script_path else "function"
        script_line = script_info
        
        return main_line, script_line

# Global instance
route_color_manager = RouteColorManager()
