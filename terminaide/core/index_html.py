# terminaide/core/index_html.py

"""
Index page functionality for Terminaide.

This module provides the HtmlIndex class which allows developers to create
navigable menu pages with ASCII art titles, keyboard navigation, and optional
grouping for organizing terminal routes.
"""

import logging
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

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


class MenuItem:
    """Single menu item with path and title."""

    def __init__(self, path: str, title: str):
        """
        Initialize a menu item.

        Args:
            path: The URL path (can be internal route or external URL)
            title: Display title for the menu item
        """
        self.path = path
        self.title = title

    def is_external(self) -> bool:
        """Check if this is an external URL."""
        return self.path.startswith(("http://", "https://"))

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {"path": self.path, "title": self.title}


class MenuGroup:
    """Group of menu items with a label."""

    def __init__(self, label: str, options: List[Dict[str, str]]):
        """
        Initialize a menu group.

        Args:
            label: The label shown for this group of menu items
            options: List of menu items as dictionaries with 'path' and 'title'
        """
        self.label = label
        self.menu_items = [MenuItem(**item) for item in options]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "label": self.label,
            "options": [item.to_dict() for item in self.menu_items],
        }


class HtmlIndex:
    """
    Configuration for an index/menu page.

    HtmlIndex allows creating navigable menu pages with ASCII art titles,
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
        # Parse menu structure
        if isinstance(menu, dict):
            # Dict format with cycle_key
            if "groups" not in menu:
                raise ValueError("Menu dict must contain 'groups' key")
            if "cycle_key" not in menu:
                raise ValueError("Menu dict must contain 'cycle_key' key")

            menu_groups = menu["groups"]
            self.cycle_key = menu["cycle_key"]

            # Validate cycle_key
            self._validate_cycle_key()
        else:
            # List format (no cycle_key)
            menu_groups = menu
            self.cycle_key = "shift+p"  # Default, won't be used if single group

        # Validate menu structure
        if not menu_groups:
            raise ValueError("Menu must contain at least one group")

        for i, group in enumerate(menu_groups):
            if not isinstance(group, dict):
                raise ValueError(f"Menu group at index {i} must be a dictionary")
            if "label" not in group:
                raise ValueError(
                    f"Menu group at index {i} missing required 'label' key"
                )
            if "options" not in group:
                raise ValueError(
                    f"Menu group at index {i} missing required 'options' key"
                )
            if not isinstance(group["options"], list):
                raise ValueError(f"Menu group at index {i} 'options' must be a list")
            if not group["options"]:
                raise ValueError(
                    f"Menu group at index {i} must have at least one option"
                )

        # Convert menu groups
        self.groups = [MenuGroup(g["label"], g["options"]) for g in menu_groups]

        # Store text/title options
        self.subtitle = subtitle
        
        # Store epititle as string (supports newlines)
        self.epititle = epititle
            
        self.title = title or "Index"
        self.supertitle = supertitle

        # Handle preview image
        if preview_image:
            self.preview_image = Path(preview_image)
        else:
            self.preview_image = None

    def _validate_cycle_key(self) -> None:
        """Validate the cycle key format."""
        valid_modifiers = {"shift", "ctrl", "alt", "meta"}
        parts = self.cycle_key.lower().split("+")

        if len(parts) != 2:
            raise ValueError(
                f"cycle_key must be in format 'modifier+key', got: {self.cycle_key}"
            )

        modifier, key = parts
        if modifier not in valid_modifiers:
            raise ValueError(
                f"Invalid modifier in cycle_key. Must be one of: {valid_modifiers}"
            )

        if not key or len(key) != 1:
            raise ValueError(
                f"Invalid key in cycle_key. Must be a single character, got: {key}"
            )

    def get_all_menu_items(self) -> List[MenuItem]:
        """
        Get all menu items as a flat list.

        Returns:
            List of all MenuItem objects across all groups
        """
        all_items = []
        for group in self.groups:
            all_items.extend(group.menu_items)
        return all_items

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

    def __repr__(self) -> str:
        """String representation for debugging."""
        item_count = len(self.get_all_menu_items())
        group_count = len(self.groups)
        return (
            f"HtmlIndex(title='{self.title}', "
            f"epititle='{self.epititle}', items={item_count}, groups={group_count})"
        )
