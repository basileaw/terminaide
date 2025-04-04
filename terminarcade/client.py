# demo/client.py
"""Example client script for terminaide.

This script demonstrates how to use terminaide's built-in games.
"""
import argparse
from terminarcade import play_snake, play_pong, play_tetris, show_index

def main():
    """Parse command-line arguments and run the selected game."""
    parser = argparse.ArgumentParser(description="Terminaide games client")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--index", 
        action="store_true", 
        help="Show the games menu"
        )
    group.add_argument(
        "--snake", 
        action="store_true", 
        help="Play Snake"
        )
    group.add_argument(
        "--pong", 
        action="store_true", 
        help="Play Pong"
        )
    group.add_argument(
        "--tetris", 
        action="store_true", 
        help="Play Tetris"
        )
    
    args = parser.parse_args()
    
    if args.snake:
        play_snake()
    elif args.pong:
        play_pong()
    elif args.tetris:
        play_tetris()
    else:
        show_index()

if __name__ == "__main__":
    main()