# terminaide/core/ascii_utils.py

"""
ASCII art generation utilities for Terminaide.

This module provides functions for generating ASCII art banners using the
ansi-shadow font from the bigfont library.
"""

import logging
from typing import Optional

logger = logging.getLogger("terminaide")


def termin_ascii(text: str) -> Optional[str]:
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
        from terminaide import termin_ascii

        banner = termin_ascii("HELLO")
        if banner:
            print(banner)
        ```

    Note:
        Uses the vendored bigfont library included with terminaide.
    """
    if not text:
        return None

    try:
        from terminaide.vendor.bigfont_slim import render
    except ImportError:
        logger.warning(
            "bigfont vendor package not found"
        )
        return None

    try:
        # Generate ASCII art using default font (ansi-shadow)
        big_letter_obj = render(text)
        if big_letter_obj is None:
            logger.error("bigfont render returned None")
            return None
        ascii_text = str(big_letter_obj)

        logger.debug(f"Generated ASCII art for text: {text}")

        # Remove ALL trailing whitespace and newlines
        ascii_text = ascii_text.rstrip()

        return ascii_text

    except Exception as e:
        logger.warning(f"Failed to generate ASCII art: {e}")
        return None
