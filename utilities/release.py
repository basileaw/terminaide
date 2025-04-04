# utilities/release.py

"""
Release script for terminaide.
Usage:
python release.py patch    # Release patch version
python release.py minor    # Release minor version
python release.py major    # Release major version
"""

import os
import argparse
import subprocess

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("type", choices=["patch", "minor", "major"],
                       help="Version type to release")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Update version
    subprocess.run(["poetry", "version", args.type], check=True)
    
    # Get new version
    version = subprocess.run(
        ["poetry", "version", "-s"],
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip()
    
    # Git commands
    subprocess.run(["git", "add", "pyproject.toml"], check=True)
    subprocess.run(["git", "commit", "-m", f"release {version}"], check=True)
    subprocess.run(["git", "tag", f"v{version}"], check=True)
    subprocess.run(["git", "push"], check=True)
    subprocess.run(["git", "push", "--tags"], check=True)
    
    # Get PyPI token and publish
    print("Please enter your PyPI token:")
    token = input()
    env = os.environ.copy()
    env["POETRY_PYPI_TOKEN_PYPI"] = token
    try:
        subprocess.run(
            ["poetry", "publish", "--build", "-vvv"],
            env=env,
            check=True
        )
    finally:
        if "POETRY_PYPI_TOKEN_PYPI" in os.environ:
            del os.environ["POETRY_PYPI_TOKEN_PYPI"]

if __name__ == "__main__":
    main()