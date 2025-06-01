# terminaide/core/index_page.py

"""
Index page functionality for Terminaide.

This module provides the IndexPage class which allows developers to create
navigable menu pages with ASCII art titles, keyboard navigation, and optional
grouping for organizing terminal routes.
"""

import logging
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

from .ascii_utils import generate_ascii_banner

logger = logging.getLogger("terminaide")


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
    """Group of menu items with optional name."""

    def __init__(self, menu: List[Dict[str, str]], name: Optional[str] = None):
        """
        Initialize a menu group.

        Args:
            menu: List of menu items as dictionaries
            name: Optional group name (shown when group is active)
        """
        self.name = name
        self.menu_items = [MenuItem(**item) for item in menu]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"menu": [item.to_dict() for item in self.menu_items]}
        if self.name:
            result["name"] = self.name
        return result


class IndexPage:
    """
    Configuration for an index/menu page.

    IndexPage allows creating navigable menu pages with ASCII art titles,
    keyboard navigation, and optional grouping. It can be used as a route
    type alongside scripts and functions in serve_apps().
    """

    def __init__(
        self,
        # Content
        menu: Optional[List[Dict[str, str]]] = None,
        groups: Optional[List[Dict[str, Any]]] = None,
        subtitle: Optional[str] = None,
        menu_title: str = "Use arrow keys to navigate, Enter to select",
        menu_subtitle: Optional[str] = None,
        # Title/ASCII options
        title: Optional[str] = None,
        page_title: Optional[str] = None,
        ascii_art: Optional[str] = None,
        supertitle: Optional[str] = None,
        # Group cycling
        cycle_key: str = "shift+p",
        # Assets
        preview_image: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize an IndexPage.

        Args:
            menu: Simple list of menu items (use this OR groups, not both)
            groups: List of menu groups for multiple sections
            subtitle: Text paragraph below the title
            menu_title: Default title shown for menus (default: "Use arrow keys to navigate, Enter to select")
                       This title is used for ungrouped menus or groups without their own name
            menu_subtitle: Optional text shown below the menu items (e.g., "[shift+g to cycle groups]")
            title: Text to convert to ASCII art using ansi-shadow font
            page_title: Browser tab title (defaults to title)
            ascii_art: Pre-made ASCII art (alternative to generated)
            supertitle: Regular text above ASCII art
            cycle_key: Key combination to cycle between groups
            preview_image: Path to preview image for social media

        Raises:
            ValueError: If both menu and groups are provided, or neither
        """
        # Validation: must have either menu or groups, not both
        if (menu is None) == (groups is None):
            raise ValueError(
                "Must provide either 'menu' or 'groups', but not both. "
                "Use 'menu' for a simple single menu, or 'groups' for multiple sections."
            )

        # Convert menu items
        if menu:
            self.menu_items = [MenuItem(**item) for item in menu]
            self.groups = None
        else:
            self.menu_items = None
            self.groups = [MenuGroup(**g) for g in groups]

        # Store text/title options
        self.subtitle = subtitle
        self.menu_title = menu_title
        self.menu_subtitle = menu_subtitle
        self.title = title
        self.page_title = page_title or title or "Index"
        self.ascii_art = ascii_art
        self.supertitle = supertitle

        # Group cycling configuration
        self.cycle_key = cycle_key

        # Handle preview image
        if preview_image:
            self.preview_image = Path(preview_image)
        else:
            self.preview_image = None

        # Validate cycle_key format
        self._validate_cycle_key()

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
        if self.menu_items:
            return self.menu_items

        all_items = []
        if self.groups:
            for group in self.groups:
                all_items.extend(group.menu_items)
        return all_items

    def to_template_context(self) -> Dict[str, Any]:
        """
        Convert to dictionary for template rendering.

        Returns:
            Dictionary with all data needed for Jinja2 template
        """
        # Generate ASCII title if needed and not provided
        title_ascii = None
        if not self.ascii_art and self.title:
            title_ascii = generate_ascii_banner(self.title)

        # Prepare groups data for JavaScript
        if self.groups:
            groups_data = [group.to_dict() for group in self.groups]
            has_groups = True
        else:
            # Single menu becomes a single unnamed group
            groups_data = [{"menu": [item.to_dict() for item in self.menu_items]}]
            has_groups = False

        # Count total items for grid sizing hints
        total_items = len(self.get_all_menu_items())

        return {
            "page_title": self.page_title,
            "ascii_art": self.ascii_art,
            "title_ascii": title_ascii,
            "supertitle": self.supertitle,
            "subtitle": self.subtitle,
            "menu_title": self.menu_title,
            "menu_subtitle": self.menu_subtitle,
            "has_groups": has_groups,
            "groups_json": groups_data,
            "cycle_key": self.cycle_key,
            "total_items": total_items,
            # Pass the original title for fallback display
            "title": self.title,
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        item_count = len(self.get_all_menu_items())
        group_count = len(self.groups) if self.groups else 1
        return (
            f"IndexPage(title='{self.title}', "
            f"items={item_count}, groups={group_count})"
        )
