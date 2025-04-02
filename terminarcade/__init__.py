"""
Games module for terminaide.

This module provides easy access to terminaide's terminal-based games.
Users can import and run games directly in their client scripts.

Example:
    from terminaide import games
    
    if __name__ == "__main__":
        # Show the games menu
        games.show_index()
        
        # Or explicitly choose a game
        games.play_snake()
        games.play_pong()
        games.play_tetris()
        games.play_asteroids()
"""

from .snake import play_snake
from .pong import play_pong
from .tetris import play_tetris
from .asteroids import play_asteroids
from .index import show_index

# Define the module's public API
__all__ = ["play_snake", "play_pong", "play_tetris", "play_asteroids", "show_index"]
