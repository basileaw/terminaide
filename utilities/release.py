# utilities/release.py

import os
import sys
import argparse
import subprocess
from getpass import getpass
from subprocess import CalledProcessError

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("type", choices=["patch", "minor", "major"], help="Version type to release")
    return parser.parse_args()

def run_command(cmd, description, exit_on_error=True, env=None):
    print(f"Executing: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
        if result.stdout.strip():
            print(result.stdout.strip())
        return result
    except CalledProcessError as e:
        print(f"Error during {description}")
        print(f"Command: {' '.join(cmd)}")
        print(f"Exit code: {e.returncode}")
        if e.stdout:
            print("Standard output:")
            print(e.stdout)
        if e.stderr:
            print("Standard error:")
            print(e.stderr)
        if exit_on_error:
            print(f"\nAborting release process due to error in {description}")
            # Cleanup: reset version if we failed after version bump
            if description == "git commit":
                subprocess.run(["git", "checkout", "pyproject.toml"], capture_output=True)
                print("Reset pyproject.toml to previous state")
            sys.exit(e.returncode)
        else:
            print(f"\nContinuing despite error in {description}")
            return None

def check_unstaged_changes():
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        print("Error: There are unstaged changes in the repository:")
        print(result.stdout)
        print("Please commit or stash these changes before running the release process.")
        sys.exit(1)

def main():
    args = parse_args()
    print("Starting Release Process")

    # Check for unstaged changes
    print("Checking for unstaged changes...")
    check_unstaged_changes()

    # Get current version before making any changes
    current_version = run_command(["poetry", "version", "-s"], "version check").stdout.strip()
    run_command(["poetry", "version", args.type], "version update")
    version_result = run_command(["poetry", "version", "-s"], "version retrieval")
    version = version_result.stdout.strip()
    tag = f"v{version}"
    print(f"New version: {version}")

    print("Git Operations")
    run_command(["git", "add", "pyproject.toml"], "git add")
    run_command(["git", "commit", "-m", f"release {version}"], "git commit")
    run_command(["git", "tag", tag], "git tag")

    push_result = run_command(["git", "push"], "git push", exit_on_error=False)
    tags_result = run_command(["git", "push", "origin", tag], "git push tag", exit_on_error=False)

    if not push_result or not tags_result:
        print("Git push operations failed. You may need to manually push commits and tags.")
        print(f"You can do this with:\n git push\n git push origin {tag}")
        proceed = input("\nDo you want to continue with package publishing anyway? (y/n): ")
    else:
        proceed = input("\nDo you want to continue with package publishing? (y/n): ")

    if proceed.lower() != 'y':
        print("Aborting release process.")
        return

    print("PyPI Publishing")
    print("Please enter your PyPI token (input will be hidden):")
    token = getpass()
    env = os.environ.copy()
    env["POETRY_PYPI_TOKEN_PYPI"] = token

    try:
        run_command(["poetry", "publish", "--build"], "poetry publish", exit_on_error=True, env=env)
        print(f"Successfully released version {version}!")
    except Exception as e:
        print(f"Error during package publishing: {str(e)}")
    finally:
        if "POETRY_PYPI_TOKEN_PYPI" in os.environ:
            del os.environ["POETRY_PYPI_TOKEN_PYPI"]

if __name__ == "__main__":
    main()