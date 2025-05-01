# __init__.py

"""
Games module for terminaide.

This module provides easy access to terminaide's terminal-based games.
Users can import and run games directly in their client scripts.

Example:
    from terminarcade import terminarcade
    
    if __name__ == "__main__":
        # Show the games menu
        terminarcade("index")
        
        # Or explicitly choose a game
        terminarcade("snake")
        terminarcade("pong")
        terminarcade("tetris")
        terminarcade("asteroids")
"""

from .snake import play_snake
from .pong import play_pong
from .tetris import play_tetris
from .asteroids import play_asteroids
from .index import show_index

def terminarcade(game_mode="index"):
    """
    Run a terminarcade game directly.
    
    Args:
        game_mode: String indicating which game to run ("index", "snake", "pong", "tetris", "asteroids")
    """
    if game_mode == "snake":
        play_snake()
    elif game_mode == "pong":
        play_pong()
    elif game_mode == "tetris":
        play_tetris()
    elif game_mode == "asteroids":
        play_asteroids()
    elif game_mode == "index":
        show_index()
    else:
        raise ValueError(f"Unknown game mode: {game_mode}")

# Define the module's public API
__all__ = ["play_snake", "play_pong", "play_tetris", "play_asteroids", "show_index", "terminarcade"]