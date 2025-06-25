# __init__.py

"""
Games module for terminaide.

This module provides easy access to terminaide's terminal-based games.
Users can import and run games directly in their client scripts.

Example:
    from terminaide.terminarcade import snake, pong, tetris, asteroids

    snake()  # Run snake game
    pong()   # Run pong game
"""

from .snake import snake
from .pong import pong
from .tetris import tetris
from .asteroids import asteroids


# Define the module's public API
__all__ = [
    "snake",
    "pong",
    "tetris",
    "asteroids",
]
