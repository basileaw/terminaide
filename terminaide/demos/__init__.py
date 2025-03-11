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
    """
    Display the default terminaide instructions.
    
    This function executes the default terminaide demo,
    showing config instructions in the terminal.
    
    Example:
        from terminaide import demos
        
        if __name__ == "__main__":
            demos.run()
    """
    _show_instructions()

def play_snake():
    """
    Run the Snake demo.
    
    This function executes the Snake game demo in the terminal.
    
    Example:
        from terminaide import demos
        
        if __name__ == "__main__":
            demos.play_snake()
    """
    _run_snake()

def play_pong():
    """
    Run the Pong demo.
    
    This function executes the Pong demo in the terminal.
    
    Example:
        from terminaide import demos
        
        if __name__ == "__main__":
            demos.play_pong()
    """
    _run_pong()

def play_tetris():
    """
    Run the Tetris game demo.
    
    This function executes the Tetris game demo in the terminal.
    
    Example:
        from terminaide import demos
        
        if __name__ == "__main__":
            demos.play_tetris()
    """
    _run_tetris()

def show_instructions():
    """
    Show the default instructions screen.
    
    This function shows the basic instructions screen that appears
    when no client script is specified.
    
    Example:
        from terminaide import demos
        
        if __name__ == "__main__":
            demos.show_instructions()
    """
    _show_instructions()

def show_index():
    """
    Show the index menu.
    
    This function displays a menu of available demos that the user
    can navigate and select from.
    
    Example:
        from terminaide import demos
        
        if __name__ == "__main__":
            demos.show_index()
    """
    _show_index()

# Expose the run function directly for backward compatibility
demos = run

# Export all the demo functions
__all__ = ["run", "play_snake", "play_pong", "play_tetris", "show_instructions", "show_index", "demos"]