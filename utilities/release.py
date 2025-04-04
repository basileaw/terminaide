# utilities/release.py
import subprocess
import os
from typing import Literal

ReleaseType = Literal["patch", "minor", "major"]

def update_version(release_type: ReleaseType) -> str:
    """Update version in pyproject.toml"""
    result = subprocess.run(
        ["poetry", "version", release_type],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip().split(' ')[-1]

def git_commands(version: str):
    """Execute git commands for committing and tagging"""
    commands = [
        ["git", "add", "pyproject.toml"],
        ["git", "commit", "-m", f"release {version}"],
        ["git", "tag", f"v{version}"],
        ["git", "push"],
        ["git", "push", "--tags"]
    ]
    
    for cmd in commands:
        subprocess.run(cmd, check=True)

def publish_to_pypi():
    """Publish to PyPI with token"""
    import getpass
    
    print("Please enter your PyPI token:")
    token = getpass.getpass()
    
    env = os.environ.copy()
    env["POETRY_PYPI_TOKEN_PYPI"] = token
    
    try:
        subprocess.run(
            ["poetry", "publish", "--build", "-vvv"],
            env=env,
            check=True
        )
    finally:
        # Ensure token is not kept in environment
        if "POETRY_PYPI_TOKEN_PYPI" in os.environ:
            del os.environ["POETRY_PYPI_TOKEN_PYPI"]

def release(release_type: ReleaseType):
    """Main release function"""
    try:
        version = update_version(release_type)
        git_commands(version)
        publish_to_pypi()
        print(f"Successfully released version {version}")
    except subprocess.CalledProcessError as e:
        print(f"Error during release process: {e}")
        raise