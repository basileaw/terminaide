# tests/client.py

"""
Example client script for terminaide.

This script demonstrates how to use the built-in terminaide demos.
You can use this as a template for creating your own custom terminal applications.
"""

import argparse
from terminaide.demos import play_snake, play_pong

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Example client script for terminaide.")

    # Add arguments
    parser.add_argument(
        "--alternate",
        action="store_true",
        help="Run an alternate behavior instead of the default demo."
    )

    # Parse arguments
    args = parser.parse_args()

    # Run the appropriate function based on arguments
    if args.alternate:
        print("Running alternate behavior...")
        play_pong()  # Run the Pong game as the alternate demo
    else:
        # Run the built-in demo (Snake game by default)
        play_snake()

if __name__ == "__main__":
    main()