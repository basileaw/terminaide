# utilities/release.py
"""
Release script for terminaide.
Usage:
python release.py patch    # Release patch version
python release.py minor    # Release minor version
python release.py major    # Release major version
"""
import os
import sys
import argparse
import subprocess
from subprocess import CalledProcessError

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("type", choices=["patch", "minor", "major"],
                       help="Version type to release")
    return parser.parse_args()

def run_command(cmd, description, exit_on_error=True):
    """Run a command with proper error handling."""
    print(f"Executing: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
        return result
    except CalledProcessError as e:
        print(f"Error during {description}:")
        print(f"Command: {' '.join(cmd)}")
        print(f"Exit code: {e.returncode}")
        if e.stdout:
            print(f"Standard output:\n{e.stdout}")
        if e.stderr:
            print(f"Standard error:\n{e.stderr}")
        
        if exit_on_error:
            print(f"Aborting release process due to error in {description}")
            sys.exit(e.returncode)
        else:
            print(f"Continuing despite error in {description}")
            return None

def main():
    args = parse_args()
    
    # Update version
    run_command(["poetry", "version", args.type], "version update")
    
    # Get new version
    version_result = run_command(
        ["poetry", "version", "-s"],
        "version retrieval"
    )
    version = version_result.stdout.strip()
    print(f"New version: {version}")
    
    # Git commands
    run_command(["git", "add", "pyproject.toml"], "git add")
    run_command(["git", "commit", "-m", f"release {version}"], "git commit")
    run_command(["git", "tag", f"v{version}"], "git tag")
    
    # Try to push, but continue even if it fails
    push_result = run_command(["git", "push"], "git push", exit_on_error=False)
    tags_result = run_command(["git", "push", "--tags"], "git push tags", exit_on_error=False)
    
    if not push_result or not tags_result:
        print("\nWarning: Git push operations failed. You may need to manually push commits and tags.")
        print("You can do this with:")
        print("  git push")
        print("  git push --tags")
        proceed = input("Do you want to continue with package publishing anyway? (y/n): ")
        if proceed.lower() != 'y':
            print("Aborting release process.")
            return
    
    # Get PyPI token and publish
    print("\nPlease enter your PyPI token:")
    token = input()
    env = os.environ.copy()
    env["POETRY_PYPI_TOKEN_PYPI"] = token
    
    try:
        run_command(
            ["poetry", "publish", "--build"],
            "poetry publish",
            exit_on_error=True,
            env=env
        )
        print(f"\nSuccessfully released version {version}!")
    except Exception as e:
        print(f"Error during package publishing: {e}")
    finally:
        # Clean up token from environment
        if "POETRY_PYPI_TOKEN_PYPI" in os.environ:
            del os.environ["POETRY_PYPI_TOKEN_PYPI"]

if __name__ == "__main__":
    main()