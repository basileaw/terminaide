# tasks.py

import os
import sys
import subprocess
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""

    BLUE = "\033[1;34m"
    GREEN = "\033[1;32m"
    GH_GREEN = "\033[32m"
    CYAN = "\033[1;36m"
    RED = "\033[1;31m"
    BOLD = "\033[1m"
    GRAY = "\033[90m"
    RESET = "\033[0m"


def load_env():
    """Load environment variables from .env file if it exists."""
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value


def run_task(command, args=None):
    """
    Execute a command with nice output and handle arguments.

    Args:
        command: The command to execute
        args: Optional arguments to append to the command
    """
    # Build the full command
    full_command = command
    if args:
        full_command = f"{command} {' '.join(args)}"

    # Print the command being executed
    print(f"Make => {Colors.BLUE}{full_command}{Colors.RESET}")

    # Load environment variables
    load_env()

    # Set PYTHONPATH
    pythonpath = os.environ.get("PYTHONPATH", "")
    if pythonpath:
        os.environ["PYTHONPATH"] = f".:{pythonpath}"
    else:
        os.environ["PYTHONPATH"] = "."

    # Execute the command
    try:
        result = subprocess.run(full_command, shell=True)
        status = result.returncode

        if status == 130:
            print(f"\n{Colors.BLUE}Process terminated by user{Colors.RESET}")
            sys.exit(0)  # Exit cleanly to prevent Make error

        sys.exit(status)
    except KeyboardInterrupt:
        print(f"\n{Colors.BLUE}Process terminated by user{Colors.RESET}")
        sys.exit(0)  # Exit cleanly to prevent Make error


def main():
    """Main entry point for the task runner."""
    if len(sys.argv) < 2:
        print("Usage: python -m tools.tasks <command> [args...]")
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else []

    # Filter out empty args
    args = [arg for arg in args if arg]

    run_task(command, args if args else None)


if __name__ == "__main__":
    main()
