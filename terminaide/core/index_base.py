# terminaide/core/index_base.py

"""
Base classes for index page functionality in Terminaide.

This module provides the base classes that allow both HTML and Curses index
implementations to share common validation, parsing, and utility logic while
maintaining identical APIs.
"""

import logging
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

logger = logging.getLogger("terminaide")


class BaseMenuItem:
    """Base menu item with path, title, and optional execution parameters."""

    def __init__(self, path: str, title: str, function=None, script=None, launcher_args=None):
        """
        Initialize a base menu item.

        Args:
            path: The URL path (can be internal route or external URL)
            title: Display title for the menu item
            function: Python function to execute when selected (optional, used by CursesIndex)
            script: Python script path to execute when selected (optional, used by CursesIndex)
            launcher_args: Additional arguments for the launcher (optional, used by CursesIndex)
        """
        self.path = path
        self.title = title
        # Optional fields used by CursesIndex, ignored by HtmlIndex
        self.function = function
        self.script = script
        self.launcher_args = launcher_args or {}

    def is_external(self) -> bool:
        """Check if this is an external URL."""
        return self.path.startswith(("http://", "https://"))

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {"path": self.path, "title": self.title}


class BaseMenuGroup:
    """Base group of menu items with a label."""

    def __init__(self, label: str, options: List[Dict[str, Any]]):
        """
        Initialize a menu group.

        Args:
            label: The label shown for this group of menu items
            options: List of menu items as dictionaries
        """
        self.label = label
        self.menu_items = [self._create_menu_item(item) for item in options]

    def _create_menu_item(self, item):
        """Create a menu item from dict. Override in subclasses for specialized items."""
        if isinstance(item, BaseMenuItem):
            return item
        else:
            # Create BaseMenuItem from dict
            return BaseMenuItem(
                path=item.get('path', ''),
                title=item.get('title', ''),
                function=item.get('function'),
                script=item.get('script'),
                launcher_args=item.get('launcher_args', {})
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "label": self.label,
            "options": [item.to_dict() for item in self.menu_items],
        }


class BaseIndex:
    """
    Base configuration for index/menu pages.

    This class provides common functionality for both HTML and Curses index
    implementations, including menu parsing, validation, and utility methods.
    """

    def __init__(
        self,
        # Content
        menu: Union[List[Dict[str, Any]], Dict[str, Any]],
        subtitle: Optional[str] = None,
        epititle: Optional[str] = None,
        # Title options
        title: Optional[str] = None,
        supertitle: Optional[str] = None,
        # Assets
        preview_image: Optional[Union[str, Path]] = None,
        # Additional args for subclass compatibility
        **kwargs
    ):
        """
        Initialize a BaseIndex.

        Args:
            menu: Either:
                - A list of menu groups (for single menu or when cycle_key not needed)
                - A dict with 'groups' and 'cycle_key' keys (for multiple menus with cycling)
                  Example: {"cycle_key": "shift+g", "groups": [{"label": "...", "options": [...]}]}
            subtitle: Text paragraph below the title
            epititle: Optional text shown below the menu items. Supports newlines for multi-line display.
            title: Title text (defaults to 'Index')
            supertitle: Regular text above title
            preview_image: Path to preview image

        Raises:
            ValueError: If menu is empty or has invalid structure
        """
        # Parse and validate menu structure
        self._parse_and_validate_menu(menu)
        
        # Store text/title options
        self.subtitle = subtitle
        self.epititle = epititle
        self.title = title or "Index"
        self.supertitle = supertitle

        # Handle preview image
        if preview_image:
            self.preview_image = Path(preview_image)
        else:
            self.preview_image = None

    def _parse_and_validate_menu(self, menu):
        """Parse and validate the menu structure."""
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
            self.cycle_key = "shift+g"  # Default, won't be used if single group

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

        # Convert menu groups - subclasses can override _create_menu_group
        self.groups = [self._create_menu_group(g["label"], g["options"]) for g in menu_groups]

    def _create_menu_group(self, label: str, options: List[Dict[str, Any]]):
        """Create a menu group. Override in subclasses for specialized groups."""
        return BaseMenuGroup(label, options)

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

    def get_all_menu_items(self) -> List[BaseMenuItem]:
        """
        Get all menu items as a flat list.

        Returns:
            List of all BaseMenuItem objects across all groups
        """
        all_items = []
        for group in self.groups:
            all_items.extend(group.menu_items)
        return all_items

    def __repr__(self) -> str:
        """String representation for debugging."""
        item_count = len(self.get_all_menu_items())
        group_count = len(self.groups)
        class_name = self.__class__.__name__
        return (
            f"{class_name}(title='{self.title}', "
            f"items={item_count}, groups={group_count})"
        )