# terminaide/core/index_html.py

"""
HTML index page functionality for Terminaide.

This module provides the HtmlIndex class which allows developers to create
navigable web menu pages with ASCII art titles, keyboard navigation, and optional
grouping for organizing terminal routes.
"""

import logging
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

from .index_base import BaseIndex, BaseMenuItem, BaseMenuGroup
from .termin_ascii import termin_ascii

logger = logging.getLogger("terminaide")


def is_ascii_art(text: str) -> bool:
    """
    Detect if a string contains ASCII art by checking for multiple lines.
    
    Args:
        text: The text to analyze
        
    Returns:
        True if the text appears to be ASCII art (multi-line), False otherwise
    """
    return '\n' in text and len(text.split('\n')) > 1


# Aliases for backward compatibility
MenuItem = BaseMenuItem
MenuGroup = BaseMenuGroup


class HtmlIndex(BaseIndex):
    """
    Configuration for an HTML index/menu page.

    HtmlIndex allows creating navigable web menu pages with ASCII art titles,
    keyboard navigation, and optional grouping. It can be used as a route
    type alongside scripts and functions in serve_apps().
    """

    def __init__(
        self,
        # Content
        menu: Union[List[Dict[str, Any]], Dict[str, Any]],
        subtitle: Optional[str] = None,
        epititle: Optional[str] = None,
        # Page title (browser tab title AND ASCII banner)
        title: Optional[str] = None,
        supertitle: Optional[str] = None,
        # Assets
        preview_image: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize an HtmlIndex.

        Args:
            menu: Either:
                - A list of menu groups (for single menu or when cycle_key not needed)
                - A dict with 'groups' and 'cycle_key' keys (for multiple menus with cycling)
                  Example: {"cycle_key": "shift+g", "groups": [{"label": "...", "options": [...]}]}
            subtitle: Text paragraph below the title
            epititle: Optional text shown below the menu items. Supports newlines for multi-line display. URLs are automatically made clickable.
            title: Browser tab title AND ASCII banner text (defaults to 'Index')
            supertitle: Regular text above ASCII art
            preview_image: Path to preview image for social media

        Raises:
            ValueError: If menu is empty or has invalid structure
        """
        # Initialize base class with all validation and parsing
        super().__init__(
            menu=menu,
            subtitle=subtitle,
            epititle=epititle,
            title=title,
            supertitle=supertitle,
            preview_image=preview_image
        )
        
        # Set default cycle_key for HTML (different from base)
        if hasattr(self, 'cycle_key') and self.cycle_key == "shift+g":
            self.cycle_key = "shift+p"

    def _create_menu_group(self, label: str, options: List[Dict[str, Any]]):
        """Create HTML-specific menu groups."""
        return BaseMenuGroup(label, options)

    def to_template_context(self) -> Dict[str, Any]:
        """
        Convert to dictionary for template rendering.

        Returns:
            Dictionary with all data needed for Jinja2 template
        """
        # Simple logic: title gets converted to ASCII art
        title_ascii = None
        
        if self.title and self.title != "Index":
            if is_ascii_art(self.title):
                # Title is already ASCII art - use it directly
                title_ascii = self.title
            else:
                # Generate ASCII art from title text
                title_ascii = termin_ascii(self.title)

        # Prepare groups data for JavaScript
        groups_data = [group.to_dict() for group in self.groups]
        has_multiple_groups = len(self.groups) > 1

        # Count total items for grid sizing hints
        total_items = len(self.get_all_menu_items())

        return {
            "page_title": self.title,
            "title_ascii": title_ascii,
            "supertitle": self.supertitle,
            "subtitle": self.subtitle,
            "epititle": self.epititle,
            "has_multiple_groups": has_multiple_groups,
            "groups_json": groups_data,
            "cycle_key": self.cycle_key,
            "total_items": total_items,
            "title": self.title,
        }

