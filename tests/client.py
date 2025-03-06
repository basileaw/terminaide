# example/client.py

"""
Example client script for terminaide.

This script demonstrates how to use the built-in terminaide demo.
You can use this as a template for creating your own custom terminal applications.
"""

import argparse
from terminaide import demos

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
        # Call your alternate function here
    else:
        # Run the built-in demo
        demos()  # Call the demo function directly

if __name__ == "__main__":
    main()
