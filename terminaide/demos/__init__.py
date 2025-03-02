# terminaide/demos/__init__.py

"""
Demo module for terminaide.

This module provides easy access to terminaide's demo functionality.
Users can import and run the demo directly in their client scripts:

Example:
    from terminaide import demo
    
    if __name__ == "__main__":
        demo.run()
"""

from .snake import run_demo

def run():
    """
    Run the terminaide demo.
    
    This function executes the default terminaide demo,
    showing a hello world application in the terminal.
    
    Example:
        from terminaide import demo
        
        if __name__ == "__main__":
            demo.run()
    """
    run_demo()

# Expose the run function directly
__all__ = ["run"]