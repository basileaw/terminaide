# tests/client.py

"""
Example client script for terminaide.

This script demonstrates how to use the built-in terminaide demos.
You can use this as a template for creating your own custom terminal applications.
"""

import argparse
from terminaide.demos import play_snake, play_pong, play_tetris, show_instructions, show_index

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Example client script for terminaide.")

    # Add arguments as mutually exclusive options
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--index",
        action="store_true",
        help="Show the demo index menu."
    )
    group.add_argument(
        "--snake",
        action="store_true",
        help="Run the Snake game demo."
    )
    group.add_argument(
        "--pong",
        action="store_true",
        help="Run the Pong demo."
    )
    group.add_argument(
        "--tetris",
        action="store_true",
        help="Run the Tetris demo."
    )
    
    # Keep the original alternate flag for backward compatibility
    group.add_argument(
        "--alternate",
        action="store_true",
        help="Run the Pong (legacy option)."
    )

    # Parse arguments
    args = parser.parse_args()

    # Run the appropriate function based on arguments
    if args.index:
        # Show the index menu
        show_index()
    elif args.snake:
        # Run the Snake demo
        play_snake()
    elif args.pong or args.alternate:
        # Run the Pong demo
        play_pong()
    elif args.tetris:
        # Run the Tetris demo
        play_tetris()
    else:
        # By default, show the instructions
        show_instructions()

if __name__ == "__main__":
    main()