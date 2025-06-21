# terminaide/core/index_html.py

"""
HTML interface implementation for AutoIndex.

This module provides the HTML template context generation for AutoIndex,
preparing data for Jinja2 templates used in web interfaces.
"""

from typing import Dict, Any
from .terminascii import terminascii
from .index_api import AutoIndex


def is_ascii_art(text: str) -> bool:
    """
    Detect if a string contains ASCII art by checking for multiple lines.
    
    Args:
        text: The text to analyze
        
    Returns:
        True if the text appears to be ASCII art (multi-line), False otherwise
    """
    return '\n' in text and len(text.split('\n')) > 1


def get_template_context(auto_index: AutoIndex) -> Dict[str, Any]:
    """
    Convert AutoIndex to dictionary for template rendering (HTML only).

    Args:
        auto_index: The AutoIndex instance to convert

    Returns:
        Dictionary with all data needed for Jinja2 template

    Raises:
        AttributeError: If called on a curses-type index
    """
    if auto_index.index_type != "html":
        raise AttributeError("get_template_context() is only available for HTML indexes")
    
    # Simple logic: title gets converted to ASCII art
    title_ascii = None
    
    if auto_index.title and auto_index.title != "Index":
        if is_ascii_art(auto_index.title):
            # Title is already ASCII art - use it directly
            title_ascii = auto_index.title
        else:
            # Generate ASCII art from title text
            title_ascii = terminascii(auto_index.title)

    # Prepare groups data for JavaScript
    groups_data = [group.to_dict() for group in auto_index.groups]
    has_multiple_groups = len(auto_index.groups) > 1

    # Count total items for grid sizing hints
    total_items = len(auto_index.get_all_menu_items())

    return {
        "page_title": auto_index.title,
        "title_ascii": title_ascii,
        "supertitle": auto_index.supertitle,
        "subtitle": auto_index.subtitle,
        "epititle": auto_index.epititle,
        "has_multiple_groups": has_multiple_groups,
        "groups_json": groups_data,
        "cycle_key": auto_index.cycle_key,
        "total_items": total_items,
        "title": auto_index.title,
    }