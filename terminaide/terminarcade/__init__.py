# __init__.py

"""
Games module for terminaide.

This module provides easy access to terminaide's terminal-based games.
Users can import and run games directly in their client scripts.

Example:
    from terminarcade import play

    if __name__ == "__main__":
        # Show the games menu
        play("index")

        # Or explicitly choose a game
        play("snake")
        play("pong")
        play("tetris")
        play("asteroids")
"""

from .snake import play_snake
from .pong import play_pong
from .tetris import play_tetris
from .asteroids import play_asteroids
from .instructions import instructions


def play(game_mode="index"):
    """
    Run a terminarcade game directly.

    Args:
        game_mode: String indicating which game to run ("index", "games", "snake", "pong", "tetris", "asteroids", "instructions")
    """
    if game_mode == "snake":
        play_snake()
    elif game_mode == "pong":
        play_pong()
    elif game_mode == "tetris":
        play_tetris()
    elif game_mode == "asteroids":
        play_asteroids()
    elif game_mode == "instructions":
        import curses
        import os

        print("\033[?25l", end="")  # Hide cursor
        os.environ.setdefault("NCURSES_NO_SETBUF", "1")
        try:
            curses.wrapper(instructions)
        finally:
            from .instructions import cleanup

            cleanup()
    else:
        raise ValueError(f"Unknown game mode: {game_mode}")


# For backward compatibility
terminarcade = play

# Define the module's public API
__all__ = [
    "play_snake",
    "play_pong",
    "play_tetris",
    "play_asteroids",
    "instructions",
    "play",
    "terminarcade",
]
