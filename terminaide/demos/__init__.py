# terminaide/demos/__init__.py

"""
Demo module for terminaide.

This module provides easy access to terminaide's demo functionality.
Users can import and run demos directly in their client scripts.

Example:
    from terminaide import demos
    
    if __name__ == "__main__":
        # Run the default demo (snake)
        demos.run()
        
        # Or explicitly choose a demo
        demos.show_index()
        demos.play_snake()
        demos.play_pong()
        demos.play_tetris()
        demos.show_instructions()
"""

from .snake import run_demo as _run_snake
from .pong import run_demo as _run_pong
from .tetris import run_demo as _run_tetris
from .instructions import run_demo as _show_instructions
from .index import run_demo as _show_index

def run():
    _show_instructions()

def play_snake():
    _run_snake()

def play_pong():
    _run_pong()

def play_tetris():
    _run_tetris()

def show_instructions():
    _show_instructions()

def show_index():
    _show_index()

demos=run
__all__=["run","play_snake","play_pong","play_tetris","show_instructions","show_index","demos"]
