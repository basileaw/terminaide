# terminaide/demos/__init__.py

"""
Demo module for terminaide.

This module provides easy access to terminaide's demo functionality.
Users can import and run demos directly in their client scripts.

Example:
    from terminaide import demos
    
    if __name__ == "__main__":
        # Run the default demo (index)
        demos.run()
        
        # Or explicitly choose a demo
        demos.show_index()
        demos.play_snake()
        demos.play_pong()
        demos.play_tetris()
"""

from .snake import run_demo as _run_snake
from .pong import run_demo as _run_pong
from .tetris import run_demo as _run_tetris
from .index import run_demo as _show_index

def run():
    # Change default demo to show the index of available demos
    _show_index()

def play_snake():
    _run_snake()

def play_pong():
    _run_pong()

def play_tetris():
    _run_tetris()

def show_index():
    _show_index()

demos = run
__all__ = ["run", "play_snake", "play_pong", "play_tetris", "show_index", "demos"]