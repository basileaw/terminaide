# terminaide/core/ascii_utils.py

"""
ASCII art generation utilities for Terminaide.

This module provides functions for generating ASCII art banners using the
ansi-shadow font from the bigfont library.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("terminaide")


def generate_ascii_banner(text: str) -> Optional[str]:
    """
    Generate ASCII art banner from text using the ansi-shadow font.

    This function creates ASCII art text that can be used for titles,
    banners, or any decorative text display in terminal applications.

    Args:
        text: The text to convert to ASCII art

    Returns:
        ASCII art string with trailing whitespace removed, or None if generation fails

    Example:
        ```python
        from terminaide import generate_ascii_banner

        banner = generate_ascii_banner("HELLO")
        if banner:
            print(banner)
        ```

    Note:
        Requires the bigfont library. Install with:
        pip install git+https://github.com/cjdurkin/bigfont.git
    """
    if not text:
        return None

    try:
        from bigfont.font import font_from_file
    except ImportError:
        logger.warning(
            "bigfont not installed. Install with: pip install git+https://github.com/cjdurkin/bigfont.git"
        )
        return None

    try:
        # Get the font file path
        misc_dir = Path(__file__).parent / "misc"
        font_file = misc_dir / "ansi-shadow.flf"

        if not font_file.exists():
            logger.error(f"Font file not found: {font_file}")
            return None

        # Load the font
        font = font_from_file(str(font_file))

        # Generate ASCII art
        big_letter_obj = font.render(text)
        ascii_text = str(big_letter_obj)

        logger.debug(f"Generated ASCII art for text: {text}")

        # Remove ALL trailing whitespace and newlines
        ascii_text = ascii_text.rstrip()

        return ascii_text

    except Exception as e:
        logger.warning(f"Failed to generate ASCII art: {e}")
        return None
